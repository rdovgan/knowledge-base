"""
Dashboard + RAG Query API — web UI for monitoring the RAG pipeline
and an HTTP API for querying the knowledge base.

Endpoints:
  GET  /              — Dashboard UI
  GET  /api/status     — Pipeline status
  POST /api/query      — Semantic search (chunks only)
  POST /api/ask        — RAG: search + LLM detailed answer
  GET  /api/ask        — RAG via GET
  GET  /api/status-rag — RAG index stats
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query as QueryParam
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn
import subprocess

app = FastAPI(title="CAKB — RAG Pipeline & Query API")

PROJECT_ROOT = Path("/home/r.dovgan/cakb")
RAG_DIR = PROJECT_ROOT / "rag"
LOG_FILE = PROJECT_ROOT / "logs" / "pipeline.log"
STATE_FILE = PROJECT_ROOT / "pipeline_state.json"
VECTORSTORE_DIR = RAG_DIR / "vectorstore"


def load_env():
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val

# ── RAG Query models ────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    # Optional metadata filter, e.g. {"module": "mbp"}
    filter: Optional[dict] = None

class QueryResponse(BaseModel):
    query: str
    total_results: int
    results: list

class AskRequest(BaseModel):
    query: str
    top_k: int = 10
    filter: Optional[dict] = None
    model: Optional[str] = None       # override default LLM model

class AskResponse(BaseModel):
    query: str
    answer: str
    model: str
    total_sources: int
    sources: list

# ── RAG Query endpoint ──────────────────────────────────────────

@app.post("/api/query", response_model=QueryResponse)
def api_query(req: QueryRequest):
    """Query the RAG knowledge base.

    Example:
        curl -X POST http://localhost:8090/api/query \
          -H 'Content-Type: application/json' \
          -d '{"query": "how does booking work?", "top_k": 5}'
    """
    from rag_pipeline.indexer import query_rag

    results = query_rag(
        query=req.query,
        store_dir=str(VECTORSTORE_DIR),
        collection_name="wiki_java",
        top_k=req.top_k,
        filter_metadata=req.filter,
    )
    return QueryResponse(
        query=req.query,
        total_results=len(results),
        results=results,
    )


@app.get("/api/query")
def api_query_get(q: str = QueryParam(..., alias="q"), top_k: int = 5):
    """Query via GET (convenient for browser / curl).

    Example:
        curl 'http://localhost:8090/api/query?q=how+does+booking+work&top_k=3'
    """
    from rag_pipeline.indexer import query_rag

    results = query_rag(
        query=q,
        store_dir=str(VECTORSTORE_DIR),
        collection_name="wiki_java",
        top_k=top_k,
    )
    return QueryResponse(query=q, total_results=len(results), results=results)


# ── RAG Ask endpoint (search + LLM answer) ──────────────────────

# Load LLM config from .env
load_env()
LLM_API_KEY = os.environ.get("ZAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
LLM_MODEL = os.environ.get("LLM_MODEL", "glm-5-turbo")
LLM_FALLBACK = os.environ.get("LLM_FALLBACK_MODEL", "glm-4.7")

SYSTEM_PROMPT = """You are a senior Java/Spring Boot architect with deep knowledge of this codebase.
Answer the user's question using ONLY the provided context from the knowledge base.
Be specific: reference actual class names, method names, package names, and configuration keys.
Explain data flows step by step. Include sequence descriptions where helpful.
If the context is insufficient to fully answer, say so and explain what you can determine.
Write in clear, structured Markdown."""


def _do_ask(query: str, top_k: int, filter_metadata: Optional[dict], model_override: Optional[str] = None):
    """Retrieve relevant chunks and generate LLM answer."""
    from rag_pipeline.indexer import query_rag

    # 1. Retrieve
    results = query_rag(
        query=query,
        store_dir=str(VECTORSTORE_DIR),
        collection_name="wiki_java",
        top_k=top_k,
        filter_metadata=filter_metadata,
    )

    if not results:
        return AskResponse(
            query=query, answer="No relevant documents found in the knowledge base.",
            model="none", total_sources=0, sources=[],
        )

    # 2. Build context
    context_parts = []
    sources = []
    for i, r in enumerate(results, 1):
        meta = r.get('metadata', {})
        source_file = meta.get('source_file', '?')
        domain = meta.get('domain', '')
        module = meta.get('module', '')
        context_parts.append(f"### Source {i}: {source_file}"
                             f"{' — ' + domain if domain else ''}" 
                             f"{' (' + module + ')' if module else ''}\n\n"
                             f"{r['text']}")
        sources.append({
            "source_file": source_file,
            "domain": domain,
            "module": module,
            "distance": round(r['distance'], 4),
        })

    context = '\n\n---\n\n'.join(context_parts)

    # 3. Call LLM
    from openai import OpenAI
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    model = model_override or LLM_MODEL
    answer = None

    for m in [model, LLM_FALLBACK]:
        if not m or m == model and answer is not None:
            continue
        try:
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"## Context from knowledge base\n\n{context}\n\n---\n\n## Question\n{query}"},
                ],
                temperature=0.3,
                max_tokens=4000,
            )
            answer = response.choices[0].message.content
            model = m
            break
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"LLM call failed for model {m}: {e}")
            continue

    if answer is None:
        answer = "LLM call failed. Try again later."

    return AskResponse(
        query=query, answer=answer, model=model,
        total_sources=len(results), sources=sources,
    )


@app.post("/api/ask", response_model=AskResponse)
def api_ask(req: AskRequest):
    """RAG query: retrieve relevant chunks + generate LLM answer.

    Example:
        curl -X POST http://localhost:8090/api/ask \
          -H 'Content-Type: application/json' \
          -d '{"query": "how does a booking flow from Booking.com through the system?", "top_k": 10}'
    """
    return _do_ask(req.query, req.top_k, req.filter, req.model)


@app.get("/api/ask")
def api_ask_get(q: str = QueryParam(..., alias="q"), top_k: int = 10):
    """RAG query via GET.

    Example:
        curl 'http://localhost:8090/api/ask?q=how+does+reservation+clarity+work&top_k=8'
    """
    return _do_ask(q, top_k, None)


def get_state():
    """Read pipeline state."""
    if not STATE_FILE.exists():
        return {"modules": [], "updated_at": ""}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"modules": [], "updated_at": ""}


def get_last_logs(n: int = 30) -> list:
    if not LOG_FILE.exists():
        return []
    try:
        lines = LOG_FILE.read_text().splitlines()
    except Exception:
        return []
    return [l for l in lines[-300:] if any(x in l for x in
            ["INFO", "ERROR", "WARNING", "═══", "✅", "❌", "⚠️",
             "Pipeline", "EXPLORING", "GENERATING", "Progress",
             "─" * 10])
            and "LiteLLM" not in l and "Wrapper" not in l
            and "litellm" not in l][-n:]


def is_running() -> tuple:
    result = subprocess.run(
        ["pgrep", "-f", "run_pipeline.py"],
        capture_output=True, text=True
    )
    pid = result.stdout.strip().split('\n')[0] if result.stdout.strip() else None
    return bool(pid), pid


def get_total_pages() -> int:
    if not RAG_DIR.exists():
        return 0
    return len([f for f in RAG_DIR.rglob("*.md")
                if f.name not in ("index.md", "README.md")])


@app.get("/api/status-rag")
def api_status_rag():
    """RAG index stats."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
        coll = client.get_collection("wiki_java")
        return {"indexed_chunks": coll.count(), "collection": "wiki_java"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/status")
def api_status():
    running, pid = is_running()
    state = get_state()

    modules_data = []
    for m in state.get("modules", []):
        pages = m.get("pages", [])
        done = [p for p in pages if p["status"] == "done"]
        failed = [p for p in pages if p["status"] == "failed"]
        pending = [p for p in pages if p["status"] == "pending"]
        generating = [p for p in pages if p["status"] == "generating"]

        modules_data.append({
            "name": m["name"],
            "status": m.get("status", "pending"),
            "completed": len(done),
            "failed": len(failed),
            "pending": len(pending),
            "generating": len(generating),
            "total": len(pages),
            "completed_pages": [p["name"] for p in done],
            "failed_pages": [p["name"] for p in failed],
            "current_page": generating[0]["name"] if generating else None,
            "explored_at": m.get("explored_at", ""),
            "completed_at": m.get("completed_at", ""),
        })

    # Stats
    total_pages = sum(m["total"] for m in modules_data)
    done_pages = sum(m["completed"] for m in modules_data)
    done_modules = sum(1 for m in modules_data if m["status"] == "done")

    return {
        "running": running,
        "pid": pid,
        "wiki_files": get_total_pages(),
        "total_pages": total_pages,
        "done_pages": done_pages,
        "done_modules": done_modules,
        "total_modules": len(modules_data),
        "progress_pct": round(done_pages / total_pages * 100, 1) if total_pages else 0,
        "updated_at": state.get("updated_at", ""),
        "modules": modules_data,
        "logs": get_last_logs(30),
    }


@app.get("/api/reset")
def api_reset():
    """Reset pipeline state."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    return {"status": "reset"}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MBP RAG Pipeline</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e0e0e0; padding: 24px; }
  h1 { font-size: 22px; font-weight: 600; color: #fff; margin-bottom: 4px; }
  .subtitle { color: #888; font-size: 13px; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .card { background: #1a1d27; border-radius: 12px; padding: 20px; border: 1px solid #2a2d3a; }
  .card-label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .card-value { font-size: 28px; font-weight: 700; color: #fff; }
  .card-value.green { color: #4ade80; }
  .card-value.yellow { color: #fbbf24; }
  .card-value.red { color: #f87171; }
  .card-value.blue { color: #60a5fa; }
  .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
  .dot-green { background: #4ade80; box-shadow: 0 0 8px #4ade80; animation: pulse 2s infinite; }
  .dot-red { background: #f87171; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }

  .modules { background: #1a1d27; border-radius: 12px; border: 1px solid #2a2d3a; margin-bottom: 24px; overflow: hidden; }
  .modules-header { padding: 16px 20px; border-bottom: 1px solid #2a2d3a; font-weight: 600; font-size: 14px; }
  .module-row { padding: 12px 20px; border-bottom: 1px solid #1e2130; transition: background .15s; cursor: pointer; }
  .module-row:last-child { border-bottom: none; }
  .module-row:hover { background: #1e2130; }
  .module-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  .module-name { font-weight: 500; font-size: 14px; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
  .badge-done { background: #14532d; color: #4ade80; }
  .badge-exploring { background: #1e3a5f; color: #60a5fa; }
  .badge-generating { background: #1e3a5f; color: #60a5fa; animation: pulse 2s infinite; }
  .badge-pending { background: #1f2937; color: #9ca3af; }
  .badge-failed { background: #450a0a; color: #f87171; }

  .module-stats { display: flex; gap: 16px; font-size: 12px; color: #9ca3af; margin-bottom: 8px; }
  .module-stats span { font-weight: 600; }
  .module-stats .done { color: #4ade80; }
  .module-stats .fail { color: #f87171; }
  .module-stats .pend { color: #fbbf24; }

  .progress-bar { height: 6px; background: #2a2d3a; border-radius: 3px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 3px; transition: width .5s; }

  .pages-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px; margin-top: 8px; }
  .page-chip { font-size: 11px; padding: 4px 8px; border-radius: 6px; background: #2a2d3a; }
  .page-chip.done { background: #14532d; color: #4ade80; }
  .page-chip.failed { background: #450a0a; color: #f87171; }
  .page-chip.pending { background: #1f2937; color: #9ca3af; }
  .page-chip.generating { background: #1e3a5f; color: #60a5fa; animation: pulse 1s infinite; }

  .logs { background: #1a1d27; border-radius: 12px; border: 1px solid #2a2d3a; overflow: hidden; }
  .logs-header { padding: 16px 20px; border-bottom: 1px solid #2a2d3a; font-weight: 600; font-size: 14px; display: flex; justify-content: space-between; align-items: center; }
  .logs-body { padding: 16px 20px; font-family: monospace; font-size: 12px; max-height: 320px; overflow-y: auto; }
  .log-line { padding: 2px 0; color: #9ca3af; line-height: 1.6; word-break: break-all; }
  .log-line.error { color: #f87171; }
  .log-line.warning { color: #fbbf24; }
  .log-line.success { color: #4ade80; }

  .btn-reset { background: #dc2626; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; }
  .btn-reset:hover { background: #ef4444; }
</style>
</head>
<body>
<h1>🚀 MBP RAG Pipeline</h1>
<p class="subtitle" id="updated">Loading...</p>

<div class="grid">
  <div class="card">
    <div class="card-label">Pipeline</div>
    <div class="card-value" id="pipeline-status">—</div>
  </div>
  <div class="card">
    <div class="card-label">Progress</div>
    <div class="card-value blue" id="progress">—</div>
  </div>
  <div class="card">
    <div class="card-label">Pages Done</div>
    <div class="card-value green" id="pages-done">—</div>
  </div>
  <div class="card">
    <div class="card-label">Modules Done</div>
    <div class="card-value" id="modules-done">—</div>
  </div>
</div>

<div class="modules">
  <div class="modules-header">📦 Modules</div>
  <div id="modules-list"></div>
</div>

<div class="logs">
  <div class="logs-header">
    <span>📋 Logs</span>
    <span class="subtitle" id="log-updated"></span>
  </div>
  <div class="logs-body" id="logs-body"></div>
</div>

<script>
function logClass(line) {
  if (line.includes('ERROR') || line.includes('❌')) return 'error';
  if (line.includes('WARNING') || line.includes('⚠')) return 'warning';
  if (line.includes('✅') || line.includes('approved') || line.includes('complete')) return 'success';
  return 'info';
}

async function refresh() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();

    // Header cards
    const running = d.running;
    document.getElementById('pipeline-status').innerHTML =
      `<span class="status-dot ${running ? 'dot-green' : 'dot-red'}"></span>${running ? 'Running' : 'Stopped'}`;
    document.getElementById('pipeline-status').className = 'card-value ' + (running ? 'green' : 'red');
    document.getElementById('progress').textContent = d.progress_pct + '%';
    document.getElementById('pages-done').textContent = d.done_pages + '/' + d.total_pages;
    document.getElementById('modules-done').textContent = d.done_modules + '/' + d.total_modules;
    document.getElementById('updated').textContent = 'Updated: ' + new Date().toLocaleTimeString();

    // Modules
    const list = document.getElementById('modules-list');
    list.innerHTML = d.modules.map(m => {
      const pct = m.total ? Math.round(m.completed / m.total * 100) : 0;
      const color = m.status === 'done' ? '#4ade80' :
                    m.status === 'generating' ? '#60a5fa' :
                    m.status === 'exploring' ? '#60a5fa' :
                    m.status === 'failed' ? '#f87171' : '#374151';
      const current = m.current_page ? ` → ${m.current_page}` : '';

      // Page chips
      let pagesHtml = '';
      if (m.total > 0) {
        // Fetch pages from module data - we'll add this to API
      }

      return `<div class="module-row">
        <div class="module-top">
          <span class="module-name">${m.name}${current}</span>
          <span class="badge badge-${m.status}">${m.status}</span>
        </div>
        <div class="module-stats">
          <span class="done">${m.completed} done</span>
          <span class="fail">${m.failed} failed</span>
          <span class="pend">${m.pending} pending</span>
          <span>${m.total} total</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <div class="pages-grid">
          ${m.completed_pages.map(p => `<div class="page-chip done">✓ ${p}</div>`).join('')}
          ${m.failed_pages.map(p => `<div class="page-chip failed">✗ ${p}</div>`).join('')}
        </div>
      </div>`;
    }).join('');

    // Logs
    const logsEl = document.getElementById('logs-body');
    const wasAtBottom = logsEl.scrollHeight - logsEl.clientHeight <= logsEl.scrollTop + 10;
    logsEl.innerHTML = d.logs.map(l =>
      `<div class="log-line ${logClass(l)}">${l}</div>`
    ).join('');
    if (wasAtBottom) logsEl.scrollTop = logsEl.scrollHeight;
    document.getElementById('log-updated').textContent = new Date().toLocaleTimeString();

  } catch(e) { console.error(e); }
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)
