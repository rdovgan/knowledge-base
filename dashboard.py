"""
Dashboard + RAG Query API — web UI for monitoring the RAG pipeline
and an HTTP API for querying the knowledge base.

Endpoints:
  GET  /              — Dashboard UI
  GET  /api/status     — Pipeline status
  POST /api/query      — Semantic search (chunks only, ?format=md for Markdown)
  GET  /api/query      — Same via GET (?q=...&format=md)
  POST /api/ask        — RAG: search + LLM answer (format=md for Markdown)
  GET  /api/ask        — Same via GET (?q=...&format=md)
  GET  /api/status-rag — RAG index stats
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query as QueryParam
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
import logging
import uvicorn
import subprocess

app = FastAPI(title="CAKB — RAG Pipeline & Query API")

log = logging.getLogger("cakb.api")

# ── In-memory API request log ───────────────────────────────────
import threading
from collections import deque
from datetime import datetime

_api_log_lock = threading.Lock()
_api_logs = deque(maxlen=200)  # keep last 200 entries

def _api_log(method: str, path: str, status: int, duration_ms: float, detail: str = ""):
    if path in ("/api/status", "/api/status-rag"):
        return
    with _api_log_lock:
        _api_logs.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": round(duration_ms, 0),
            "detail": detail,
        })

@app.get("/api/logs")
def api_get_logs():
    with _api_log_lock:
        return list(_api_logs)

PROJECT_ROOT = Path("/home/r.dovgan/cakb")
RAG_DIR = PROJECT_ROOT / "rag"          # wiki markdown (submodule)
DATA_DIR = PROJECT_ROOT / "data"        # pipeline data (outside submodule, git-safe)
LOG_FILE = PROJECT_ROOT / "logs" / "pipeline.log"
STATE_FILE = PROJECT_ROOT / "pipeline_state.json"
VECTORSTORE_DIR = DATA_DIR / "vectorstore"


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
    format: Optional[str] = None  # "md" for human-readable Markdown response

class QueryResponse(BaseModel):
    query: str
    total_results: int
    results: list

class AskRequest(BaseModel):
    query: str
    top_k: int = 10
    filter: Optional[dict] = None
    model: Optional[str] = None       # override default LLM model
    format: Optional[str] = None      # "md" for human-readable Markdown response

class AskResponse(BaseModel):
    query: str
    answer: str
    model: str
    total_sources: int
    sources: list

# ── RAG Query endpoint ──────────────────────────────────────────

@app.post("/api/query")
def api_query(req: QueryRequest):
    """Query the RAG knowledge base.

    Example:
        curl -X POST http://localhost:8090/api/query \
          -H 'Content-Type: application/json' \
          -d '{"query": "how does booking work?", "top_k": 5, "format": "md"}'
    """
    from rag_pipeline.indexer import query_rag

    results = query_rag(
        query=req.query,
        store_dir=str(VECTORSTORE_DIR),
        collection_name="wiki_java",
        top_k=req.top_k,
        filter_metadata=req.filter,
    )
    _api_log("POST", "/api/query", 200, 0, req.query[:80])
    resp = QueryResponse(
        query=req.query,
        total_results=len(results),
        results=results,
    )
    if req.format == "md":
        return PlainTextResponse(_format_query_md(resp), media_type="text/markdown")
    if req.format == "human":
        return PlainTextResponse(_humanize_query(resp), media_type="text/markdown")
    return resp


@app.get("/api/query")
def api_query_get(q: str = QueryParam(..., alias="q"), top_k: int = 5, format: Optional[str] = None):
    """Query via GET (convenient for browser / curl).

    Example:
        curl 'http://localhost:8090/api/query?q=how+does+booking+work&top_k=3&format=md'
    """
    from rag_pipeline.indexer import query_rag

    results = query_rag(
        query=q,
        store_dir=str(VECTORSTORE_DIR),
        collection_name="wiki_java",
        top_k=top_k,
    )
    _api_log("GET", "/api/query", 200, 0, q[:80])
    resp = QueryResponse(query=q, total_results=len(results), results=results)
    if format == "md":
        return PlainTextResponse(_format_query_md(resp), media_type="text/markdown")
    if format == "human":
        return PlainTextResponse(_humanize_query(resp), media_type="text/markdown")
    return resp


# ── RAG Ask endpoint (search + LLM answer) ──────────────────────

# Load LLM config from .env
load_env()
LLM_API_KEY = os.environ.get("ZAI_API_KEY", "")

# ── Startup integrity check ───────────────────────────────────────

def _check_vectorstore():
    """Warn if vectorstore is missing or empty."""
    if not VECTORSTORE_DIR.is_dir():
        log.warning(f"Vectorstore dir not found: {VECTORSTORE_DIR}. API will return empty results.")
        return
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
        for coll in client.list_collections():
            count = coll.count()
            if count == 0:
                log.warning(f"Collection '{coll.name}' is empty. Run: python3 run_rag.py index")
            else:
                log.info(f"Vectorstore OK: {coll.name} = {count} chunks")
    except Exception as e:
        log.warning(f"Vectorstore check failed: {e}")

_check_vectorstore()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
LLM_MODEL = os.environ.get("LLM_MODEL", "glm-5-turbo")
LLM_FALLBACK = os.environ.get("LLM_FALLBACK_MODEL", "glm-4.7")

SYSTEM_PROMPT = """You are a senior Java/Spring Boot architect with deep knowledge of this codebase.
Answer the user's question using ONLY the provided context from the knowledge base.
Be specific: reference actual class names, method names, package names, and configuration keys.
Explain data flows step by step. Include sequence descriptions where helpful.
If the context includes flow documents (type: flow), use them as the primary source for process questions.
If the context is insufficient to fully answer, say so and explain what you can determine.
Write in clear, structured Markdown."""


def _extract_keywords(query: str) -> list:
    """Extract meaningful keywords from a query, dropping stopwords."""
    import re
    stopwords = {'how', 'does', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does',
                 'what', 'where', 'when', 'why', 'who', 'which', 'can', 'could', 'would',
                 'should', 'will', 'shall', 'may', 'might', 'must', 'in', 'on', 'at', 'to',
                 'for', 'of', 'with', 'by', 'from', 'it', 'its', 'this', 'that', 'and',
                 'or', 'but', 'not', 'no', 'if', 'then', 'than', 'so', 'as', 'up', 'out',
                 'about', 'into', 'over', 'after', 'work', 'working', 'system', 'flow',
                 'process', 'please', 'explain', 'describe', 'tell', 'me', 'through'}
    words = re.findall(r'[a-zA-Z_]+', query.lower())
    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    return keywords


def _keyword_search(keywords: list, top_k: int) -> list:
    """Search ChromaDB by keyword containment — finds docs that mention specific terms."""
    import chromadb

    client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
    try:
        collection = client.get_collection("wiki_java")
    except Exception:
        return []

    results = []
    for kw in keywords:
        try:
            r = collection.get(
                where_document={"$contains": kw},
                include=["documents", "metadatas"],
                limit=top_k,
            )
            for i in range(len(r['ids'])):
                results.append({
                    'id': r['ids'][i],
                    'text': r['documents'][i],
                    'metadata': r['metadatas'][i],
                    'distance': 1.0,  # keyword matches get distance 1.0
                    '_keyword': kw,
                })
        except Exception:
            continue

    return results


def _multi_query_retrieve(query: str, top_k: int, filter_metadata: Optional[dict]) -> list:
    """Hybrid retrieval: semantic search + keyword search, merged & deduped."""
    from rag_pipeline.indexer import query_rag

    seen = set()
    all_results = []

    def _add(r):
        dedup_key = r.get('metadata', {}).get('source_file', '') + ':' + r['text'][:100]
        if dedup_key not in seen:
            seen.add(dedup_key)
            all_results.append(r)

    # 1. Semantic search with original query
    for r in query_rag(query=query, store_dir=str(VECTORSTORE_DIR),
                       collection_name="wiki_java", top_k=top_k, filter_metadata=filter_metadata):
        _add(r)

    # 2. Keyword search — extract terms and find docs containing them
    keywords = _extract_keywords(query)
    kw_results = _keyword_search(keywords, top_k)
    for r in kw_results:
        _add(r)

    # 3. Semantic search with keyword-focused sub-queries
    if keywords:
        # Combine keywords into meaningful pairs
        sub_queries = []
        if len(keywords) >= 2:
            sub_queries.append(' '.join(keywords[:4]))  # first 4 keywords
        # Add CamelCase variant (e.g., "inquiry reservation" → "InquiryReservation")
        sub_queries.append(''.join(k.capitalize() for k in keywords[:3]))
        # Add class-search variant
        sub_queries.append('class ' + ' '.join(keywords[:3]))

        for sq in sub_queries:
            for r in query_rag(query=sq, store_dir=str(VECTORSTORE_DIR),
                               collection_name="wiki_java", top_k=top_k // 2, filter_metadata=filter_metadata):
                _add(r)

    # Sort: semantic results by distance, keyword results after
    all_results.sort(key=lambda x: x['distance'])
    return all_results


EXPANSION_PROMPT = """UNUSED"""


def _format_query_md(resp: QueryResponse) -> str:
    """Render QueryResponse as human-readable Markdown."""
    lines = [
        f"# Search Results",
        f"",
        f"**Query:** {resp.query}  ",
        f"**Results:** {resp.total_results}",
        f"",
        f"---",
        f"",
    ]
    for i, r in enumerate(resp.results, 1):
        meta = r.get('metadata', {}) if isinstance(r, dict) else {}
        source = meta.get('source_file', '—')
        domain = meta.get('domain', '')
        module = meta.get('module', '')
        distance = r.get('distance', '—') if isinstance(r, dict) else '—'
        text = r.get('text', str(r)) if isinstance(r, dict) else str(r)

        lines.append(f"## Result {i}")
        lines.append("")
        lines.append(f"**Source:** `{source}`  ")
        if domain:
            lines.append(f"**Domain:** {domain}  ")
        if module:
            lines.append(f"**Module:** {module}  ")
        lines.append(f"**Distance:** {distance}")
        lines.append("")
        lines.append(text)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _format_ask_md(resp: AskResponse) -> str:
    """Render AskResponse as human-readable Markdown."""
    lines = [
        f"# Answer",
        f"",
        f"**Query:** {resp.query}  ",
        f"**Model:** {resp.model}  ",
        f"**Sources used:** {resp.total_sources}",
        f"",
        f"---",
        f"",
        resp.answer,
        f"",
        f"---",
        f"",
        f"## Sources",
        f""]
    for i, s in enumerate(resp.sources, 1):
        source = s.get('source_file', '—') if isinstance(s, dict) else '—'
        domain = s.get('domain', '') if isinstance(s, dict) else ''
        module = s.get('module', '') if isinstance(s, dict) else ''
        distance = s.get('distance', '—') if isinstance(s, dict) else '—'
        lines.append(f"{i}. **{source}**")
        if domain or module:
            parts = []
            if domain:
                parts.append(f"domain: {domain}")
            if module:
                parts.append(f"module: {module}")
            lines.append(f"   _{', '.join(parts)}_  ")
        lines.append(f"   distance: `{distance}`")
    lines.append("")
    return "\n".join(lines)


def _humanize_ask(resp: AskResponse) -> str:
    """Call LLM to rewrite AskResponse as polished human-readable Markdown."""
    from openai import OpenAI
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    sources_text = "\n".join(
        f"- {s.get('source_file', '?')} ({s.get('domain', '')} / {s.get('module', '')})"
        for s in resp.sources
    )
    payload = (
        f"## Question\n{resp.query}\n\n"
        f"## Answer\n{resp.answer}\n\n"
        f"## Sources\n{sources_text}"
    )
    prompt = (
        "You are a technical writer. Rewrite the following knowledge base response "
        "into clear, well-structured Markdown for a non-expert reader. "
        "Use headings, bullet points, and plain language. "
        "Omit raw file paths and distance scores unless essential. Be concise.\n\n"
        + payload
    )
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=4000,
        )
        return response.choices[0].message.content
    except Exception:
        return _format_ask_md(resp)


def _humanize_query(resp: QueryResponse) -> str:
    """Call LLM to synthesize QueryResponse chunks into human-readable Markdown."""
    from openai import OpenAI
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    chunks = "\n\n---\n\n".join(
        r.get('text', str(r)) if isinstance(r, dict) else str(r)
        for r in resp.results
    )
    payload = f"## Search query\n{resp.query}\n\n## Retrieved chunks\n\n{chunks}"
    prompt = (
        "You are a technical writer. Synthesize the following retrieved knowledge base chunks "
        "into a single clear, well-structured Markdown document for a non-expert reader. "
        "Use headings and bullet points. Avoid repeating the same information. Be concise.\n\n"
        + payload
    )
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=4000,
        )
        return response.choices[0].message.content
    except Exception:
        return _format_query_md(resp)


def _expand_query(query: str, client) -> list:
    """Not used — kept for compatibility."""
    return [query]


def _do_ask(query: str, top_k: int, filter_metadata: Optional[dict], model_override: Optional[str] = None, expand: bool = True):
    """Retrieve relevant chunks (with query expansion) and generate LLM answer."""
    from rag_pipeline.indexer import query_rag
    from openai import OpenAI

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    # 2. Hybrid retrieval: semantic + keyword
    all_results = _multi_query_retrieve(query, top_k, filter_metadata)

    if not all_results:
        return AskResponse(
            query=query, answer="No relevant documents found in the knowledge base.",
            model="none", total_sources=0, sources=[],
        )

    # 3. Build context (top N results after dedup)
    max_context_results = min(len(all_results), top_k * 3)  # Allow more context
    context_parts = []
    sources = []
    for i, r in enumerate(all_results[:max_context_results], 1):
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

    # 4. Call LLM with full context
    model = model_override or LLM_MODEL
    answer = None

    for m in [model, LLM_FALLBACK]:
        if not m or (m == model and answer is not None):
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
        total_sources=len(all_results[:max_context_results]), sources=sources,
    )


@app.post("/api/ask")
def api_ask(req: AskRequest):
    """RAG query: retrieve relevant chunks + generate LLM answer.

    Example:
        curl -X POST http://localhost:8090/api/ask \
          -H 'Content-Type: application/json' \
          -d '{"query": "how does a booking flow from Booking.com through the system?", "top_k": 10, "format": "md"}'
    """
    start = datetime.now()
    try:
        result = _do_ask(req.query, req.top_k, req.filter, req.model)
        duration = (datetime.now() - start).total_seconds() * 1000
        _api_log("POST", "/api/ask", 200, duration, req.query[:80])
        if req.format == "md":
            return PlainTextResponse(_format_ask_md(result), media_type="text/markdown")
        if req.format == "human":
            return PlainTextResponse(_humanize_ask(result), media_type="text/markdown")
        return result
    except Exception as e:
        duration = (datetime.now() - start).total_seconds() * 1000
        _api_log("POST", "/api/ask", 500, duration, f"ERROR: {e}")
        log.exception(f"/api/ask failed: {e}")
        return PlainTextResponse(f"Internal error: {e}", status_code=500)


@app.get("/api/ask")
def api_ask_get(q: str = QueryParam(..., alias="q"), top_k: int = 10, format: Optional[str] = None):
    """RAG query via GET.

    Example:
        curl 'http://localhost:8090/api/ask?q=how+does+reservation+clarity+work&top_k=8&format=md'
    """
    start = datetime.now()
    result = _do_ask(q, top_k, None)
    duration = (datetime.now() - start).total_seconds() * 1000
    _api_log("GET", "/api/ask", 200, duration, q[:80])
    if format == "md":
        return PlainTextResponse(_format_ask_md(result), media_type="text/markdown")
    if format == "human":
        return PlainTextResponse(_humanize_ask(result), media_type="text/markdown")
    return result


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
    start = datetime.now()
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
        coll = client.get_collection("wiki_java")
        result = {"indexed_chunks": coll.count(), "collection": "wiki_java"}
    except Exception as e:
        result = {"error": str(e)}
    duration = (datetime.now() - start).total_seconds() * 1000
    _api_log("GET", "/api/status-rag", 200, duration)
    return result


@app.get("/api/status")
def api_status():
    start = datetime.now()
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

    result = {
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
    duration = (datetime.now() - start).total_seconds() * 1000
    _api_log("GET", "/api/status", 200, duration)
    return result


@app.get("/api/reset")
def api_reset():
    """Reset pipeline state."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    _api_log("GET", "/api/reset", 200, 0)
    return {"status": "reset"}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CAKB — RAG Pipeline & Query API</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e0e0e0; padding: 24px; max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 22px; font-weight: 600; color: #fff; margin-bottom: 4px; display: inline; }
  .subtitle { color: #888; font-size: 13px; margin-bottom: 24px; }
  .header-row { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
  .btn-help { background: #2563eb; color: #fff; border: none; padding: 5px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600; }
  .btn-help:hover { background: #3b82f6; }

  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .card { background: #1a1d27; border-radius: 12px; padding: 20px; border: 1px solid #2a2d3a; }
  .card-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  .card-value { font-size: 24px; font-weight: 700; color: #fff; }
  .card-value.green { color: #4ade80; }
  .card-value.red { color: #f87171; }
  .card-value.blue { color: #60a5fa; }
  .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
  .dot-green { background: #4ade80; box-shadow: 0 0 8px #4ade80; animation: pulse 2s infinite; }
  .dot-red { background: #f87171; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }

  .section { background: #1a1d27; border-radius: 12px; border: 1px solid #2a2d3a; margin-bottom: 24px; overflow: hidden; }
  .section-header { padding: 14px 20px; border-bottom: 1px solid #2a2d3a; font-weight: 600; font-size: 14px; display: flex; justify-content: space-between; align-items: center; }
  .section-body { padding: 0; }

  .module-row { display: flex; align-items: center; gap: 8px; padding: 4px 12px; font-size: 12px; border-bottom: 1px solid #1e213066; }
  .module-row:last-child { border-bottom: none; }
  .module-row:hover { background: #1e2130; }
  .module-name { font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .badge { min-width: 56px; text-align: center; flex-shrink: 0; }
  .module-chevron { display: none; }
  .module-content { display: none; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 10px; font-weight: 600; }
  .badge-done { background: #14532d; color: #4ade80; }
  .badge-generating { background: #1e3a5f; color: #60a5fa; animation: pulse 2s infinite; }
  .badge-pending { background: #1f2937; color: #9ca3af; }
  .badge-failed { background: #450a0a; color: #f87171; }
  .module-bar { width: 50px; height: 3px; background: #2a2d3a; border-radius: 2px; overflow: hidden; flex-shrink: 0; }
  .module-bar-fill { height: 100%; border-radius: 2px; }
  .module-pct { color: #6b7280; width: 30px; text-align: right; flex-shrink: 0; font-size: 11px; }
  .module-counts { color: #6b7280; font-size: 11px; white-space: nowrap; flex-shrink: 0; }
  .collapsed { display: none !important; }
  .progress-bar { height: 6px; background: #2a2d3a; border-radius: 3px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 3px; transition: width .5s; }
  .pages-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px; margin-top: 8px; }
  .page-chip { font-size: 11px; padding: 4px 8px; border-radius: 6px; background: #2a2d3a; }
  .page-chip.failed { background: #450a0a; color: #f87171; }
  .page-chip.generating { background: #1e3a5f; color: #60a5fa; animation: pulse 1s infinite; }

  .log-body { padding: 12px 20px; font-family: 'Menlo', 'Consolas', monospace; font-size: 12px; max-height: 300px; overflow-y: auto; }
  .log-line { padding: 2px 0; color: #9ca3af; line-height: 1.6; white-space: pre-wrap; word-break: break-all; }
  .log-line.error { color: #f87171; }
  .log-line.warning { color: #fbbf24; }
  .log-line.success { color: #4ade80; }

  /* API log table */
  .api-log-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: 'Menlo', 'Consolas', monospace; }
  .api-log-table th { text-align: left; color: #6b7280; font-weight: 600; padding: 8px 12px; border-bottom: 1px solid #2a2d3a; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
  .api-log-table td { padding: 6px 12px; border-bottom: 1px solid #1e2130; vertical-align: top; }
  .api-log-table tr:hover { background: #1e2130; }
  .status-ok { color: #4ade80; }
  .status-err { color: #f87171; }
  .method-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 700; }
  .method-get { background: #1e3a5f; color: #60a5fa; }
  .method-post { background: #14532d; color: #4ade80; }

  /* Help modal */
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1000; justify-content: center; align-items: center; }
  .modal-overlay.active { display: flex; }
  .modal { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 16px; max-width: 720px; width: 90%; max-height: 85vh; overflow-y: auto; padding: 0; }
  .modal-title { padding: 20px 24px; border-bottom: 1px solid #2a2d3a; display: flex; justify-content: space-between; align-items: center; }
  .modal-title h2 { font-size: 18px; color: #fff; }
  .modal-close { background: none; border: none; color: #6b7280; font-size: 20px; cursor: pointer; padding: 4px 8px; border-radius: 6px; }
  .modal-close:hover { background: #2a2d3a; color: #fff; }
  .modal-body { padding: 20px 24px; }
  .api-section { margin-bottom: 24px; }
  .api-section h3 { color: #60a5fa; font-size: 14px; margin-bottom: 8px; }
  .api-section p { color: #9ca3af; font-size: 13px; margin-bottom: 10px; line-height: 1.5; }
  .code-block { background: #0f1117; border: 1px solid #2a2d3a; border-radius: 8px; padding: 14px 16px; font-family: 'Menlo', 'Consolas', monospace; font-size: 12px; color: #e0e0e0; overflow-x: auto; position: relative; margin-bottom: 8px; white-space: pre; line-height: 1.6; }
  .btn-copy { position: absolute; top: 8px; right: 8px; background: #2a2d3a; color: #9ca3af; border: none; padding: 3px 8px; border-radius: 4px; font-size: 10px; cursor: pointer; }
  .btn-copy:hover { background: #3b4252; color: #fff; }
  .param-table { width: 100%; font-size: 12px; margin-bottom: 12px; }
  .param-table td { padding: 4px 8px; border-bottom: 1px solid #1e2130; }
  .param-table td:first-child { color: #fbbf24; font-family: monospace; white-space: nowrap; }
  .param-table td:last-child { color: #9ca3af; }
  .response-hint { color: #6b7280; font-size: 11px; font-style: italic; margin-top: 4px; }

  /* Query form */
  .query-form { padding: 16px 20px; }
  .query-row { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 12px; }
  .query-input { flex: 1; background: #0f1117; border: 1px solid #2a2d3a; border-radius: 8px; padding: 10px 14px; color: #e0e0e0; font-size: 14px; font-family: 'Segoe UI', sans-serif; outline: none; transition: border-color .2s; }
  .query-input:focus { border-color: #2563eb; }
  .query-input::placeholder { color: #4b5563; }
  .btn-send { background: #2563eb; color: #fff; border: none; padding: 10px 22px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; white-space: nowrap; transition: background .15s; }
  .btn-send:hover { background: #3b82f6; }
  .btn-send:disabled { background: #1e3a5f; color: #6b7280; cursor: not-allowed; }
  .query-opts { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
  .opt-group { display: flex; align-items: center; gap: 8px; }
  .opt-group label { font-size: 12px; color: #9ca3af; cursor: pointer; display: flex; align-items: center; gap: 5px; }
  .opt-group select, .opt-group input[type=number] { background: #0f1117; border: 1px solid #2a2d3a; border-radius: 6px; color: #e0e0e0; padding: 4px 8px; font-size: 12px; outline: none; }
  .opt-group select:focus, .opt-group input[type=number]:focus { border-color: #2563eb; }
  .radio-pill { display: none; }
  .radio-pill + span { display: inline-block; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #2a2d3a; color: #6b7280; transition: all .15s; }
  .radio-pill:checked + span { background: #1e3a5f; border-color: #2563eb; color: #60a5fa; }
  .radio-green:checked + span { background: #14532d; border-color: #22c55e; color: #4ade80; }
  .checkbox-pill { display: none; }
  .checkbox-pill + span { display: inline-block; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid #2a2d3a; color: #6b7280; transition: all .15s; cursor: pointer; }
  .checkbox-pill:checked + span { background: #14532d; border-color: #22c55e; color: #4ade80; }
  .result-wrap { position: relative; }
  .result-area { width: 100%; min-height: 160px; max-height: 500px; background: #0f1117; border: 1px solid #2a2d3a; border-radius: 8px; padding: 12px 14px; color: #e0e0e0; font-family: 'Menlo','Consolas',monospace; font-size: 12px; line-height: 1.6; resize: vertical; outline: none; }
  .result-area:focus { border-color: #2563eb; }
  .result-area::placeholder { color: #4b5563; }
  .btn-copy-result { position: absolute; top: 8px; right: 8px; background: #2a2d3a; color: #9ca3af; border: none; padding: 5px 12px; border-radius: 6px; font-size: 11px; cursor: pointer; transition: all .15s; }
  .btn-copy-result:hover { background: #3b4252; color: #fff; }
  .result-meta { display: flex; gap: 16px; margin-top: 6px; font-size: 11px; color: #6b7280; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #fff; border-top-color: transparent; border-radius: 50%; animation: spin .6s linear infinite; vertical-align: middle; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="header-row">
  <h1>🚀 CAKB — RAG Pipeline</h1>
  <button class="btn-help" onclick="toggleModal(true)">💡 API Examples</button>
</div>
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
  <div class="card">
    <div class="card-label">Index Chunks</div>
    <div class="card-value blue" id="rag-chunks">—</div>
  </div>
</div>

<div class="section">
  <div class="section-header">🔍 Query Knowledge Base</div>
  <div class="query-form">
    <div class="query-row">
      <input class="query-input" id="q-input" type="text" placeholder="Ask a question or search the knowledge base…" onkeydown="if(event.key==='Enter')sendQuery()">
      <button class="btn-send" id="btn-send" onclick="sendQuery()">Send</button>
    </div>
    <div class="query-opts">
      <div class="opt-group">
        <label><input type="radio" name="q-endpoint" class="radio-pill" value="ask" checked><span>Ask (LLM)</span></label>
        <label><input type="radio" name="q-endpoint" class="radio-pill" value="query"><span>Search</span></label>
      </div>
      <div class="opt-group">
        <label><input type="radio" name="q-format" class="radio-pill radio-green" value=""><span>JSON</span></label>
        <label><input type="radio" name="q-format" class="radio-pill radio-green" value="md" checked><span>Markdown</span></label>
        <label><input type="radio" name="q-format" class="radio-pill radio-green" value="human"><span>Human</span></label>
      </div>
      <div class="opt-group">
        <label>top_k <input type="number" id="q-topk" value="10" min="1" max="50" style="width:60px"></label>
      </div>
    </div>
    <div class="result-wrap">
      <textarea class="result-area" id="q-result" readonly placeholder="Results will appear here…"></textarea>
      <button class="btn-copy-result" id="btn-copy-result" onclick="copyResult()">📋 Copy</button>
    </div>
    <div class="result-meta" id="q-meta"></div>
  </div>
</div>

<div class="section">
  <div class="section-header">
    <span>🔗 API Requests</span>
    <span style="font-size:11px;color:#6b7280" id="api-log-count"></span>
  </div>
  <div class="section-body" style="max-height:300px;overflow-y:auto" id="api-log-body">
    <table class="api-log-table">
      <thead><tr><th>Time</th><th></th><th>Endpoint</th><th>Status</th><th>Duration</th><th>Detail</th></tr></thead>
      <tbody id="api-log-tbody"></tbody>
    </table>
  </div>
</div>

<div class="section">
  <div class="section-header">
    <span>📋 Pipeline Logs</span>
    <span style="font-size:11px;color:#6b7280" id="log-updated"></span>
  </div>
  <div class="log-body" id="logs-body"></div>
</div>

<div class="section">
  <div class="section-header" onclick="document.getElementById('modules-list').classList.toggle('collapsed')" style="cursor:pointer">
    <span>📦 Modules</span>
    <span style="font-size:11px;color:#6b7280" id="modules-summary"></span>
  </div>
  <div class="section-body collapsed" id="modules-list" style="max-height:250px;overflow-y:auto"></div>
</div>

<!-- Help Modal -->
<div class="modal-overlay" id="help-modal" onclick="if(event.target===this)toggleModal(false)">
  <div class="modal">
    <div class="modal-title">
      <h2>💡 API Examples</h2>
      <button class="modal-close" onclick="toggleModal(false)">✕</button>
    </div>
    <div class="modal-body">

      <div class="api-section">
        <h3>POST /api/ask — RAG Query (search + LLM answer)</h3>
        <p>The main endpoint. Sends a natural language question, retrieves relevant code context, and generates a detailed answer with class/method references.</p>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl -X POST http://localhost:8090/api/ask \\
  -H 'Content-Type: application/json' \\
  -d '{
    "query": "How does inquiry reservation work?",
    "top_k": 10
  }'</div>
        <table class="param-table">
          <tr><td>query</td><td>string — Your question in plain English</td></tr>
          <tr><td>top_k</td><td>int, default 10 — Number of chunks to retrieve</td></tr>
          <tr><td>filter</td><td>object, optional — Metadata filter, e.g. {"module": "mbp"}</td></tr>
          <tr><td>model</td><td>string, optional — Override LLM model name</td></tr>
          <tr><td>format</td><td>string, optional — &quot;md&quot; for template Markdown, &quot;human&quot; for LLM-rewritten Markdown</td></tr>
        </table>
        <p class="response-hint">Returns JSON: { query, answer, model, total_sources, sources[] } — or Markdown when format=md/human</p>
      </div>

      <div class="api-section">
        <h3>GET /api/ask — Quick RAG via URL params</h3>
        <p>Same as POST but via GET — handy for quick browser tests. Add <code>&amp;format=md</code> for readable Markdown.</p>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl 'http://localhost:8090/api/ask?q=how+does+booking+work&top_k=8&format=md'</div>
      </div>

      <div class="api-section">
        <h3>POST /api/query — Semantic Search (chunks only, no LLM)</h3>
        <p>Returns raw matching chunks with distance scores. Useful when you need source documents without an LLM summary.</p>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl -X POST http://localhost:8090/api/query \\
  -H 'Content-Type: application/json' \\
  -d '{
    "query": "ReservationNightlyRateRequest",
    "top_k": 5,
    "filter": {"module": "mbp"}
  }'</div>
        <table class="param-table">
          <tr><td>query</td><td>string — Search query text</td></tr>
          <tr><td>top_k</td><td>int, default 5 — Number of results</td></tr>
          <tr><td>filter</td><td>object, optional — Metadata filter, e.g. {&quot;module&quot;: &quot;mbp&quot;}</td></tr>
          <tr><td>format</td><td>string, optional — &quot;md&quot; for template Markdown, &quot;human&quot; for LLM-synthesized Markdown</td></tr>
        </table>
        <p class="response-hint">Returns JSON: { query, total_results, results[] } — or Markdown when format=md/human</p>
      </div>

      <div class="api-section">
        <h3>GET /api/query — Quick search via URL params</h3>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl 'http://localhost:8090/api/query?q=InquiryReservation&top_k=3&format=md'</div>
      </div>

      <div class="api-section">
        <h3>GET /api/status — Pipeline Status</h3>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl http://localhost:8090/api/status</div>
      </div>

      <div class="api-section">
        <h3>GET /api/status-rag — RAG Index Stats</h3>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl http://localhost:8090/api/status-rag</div>
      </div>

      <div class="api-section">
        <h3>GET /api/logs — Recent API Request Log</h3>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl http://localhost:8090/api/logs</div>
      </div>

      <div class="api-section" style="margin-bottom:0">
        <h3>Python Example</h3>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>import requests

# JSON response
resp = requests.post("http://localhost:8090/api/ask", json={
    "query": "How does the pricing engine calculate nightly rates?",
    "top_k": 10
})
data = resp.json()
print(data["answer"])        # Markdown answer
print(data["total_sources"])  # Number of source chunks used

# Human-readable Markdown response
resp = requests.post("http://localhost:8090/api/ask", json={
    "query": "How does the pricing engine calculate nightly rates?",
    "top_k": 10,
    "format": "md"
})
print(resp.text)  # Full Markdown document with answer + sources</div>
      </div>

    </div>
  </div>
</div>

<script>
function toggleModule(header) {
  const content = header.nextElementSibling;
  const chevron = header.querySelector('.module-chevron');
  content.classList.toggle('expanded');
  chevron.classList.toggle('expanded');
}

function toggleModal(show) {
  document.getElementById('help-modal').classList.toggle('active', show);
}

function _copyText(text, btn, okLabel, origLabel) {
  // Fallback that works in non-HTTPS (IP address) contexts
  try { navigator.clipboard.writeText(text).then(() => { btn.textContent = okLabel; setTimeout(() => btn.textContent = origLabel, 1500); }); }
  catch(e) { const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta); btn.textContent = okLabel; setTimeout(() => btn.textContent = origLabel, 1500); }
}

function copyCode(btn) {
  const clone = btn.parentElement.cloneNode(true);
  clone.querySelector('.btn-copy')?.remove();
  const code = clone.textContent.trim();
  _copyText(code, btn, '✓', 'Copy');
}

function pipelineLogClass(line) {
  if (line.includes('ERROR') || line.includes('❌')) return 'error';
  if (line.includes('WARNING') || line.includes('⚠')) return 'warning';
  if (line.includes('✅') || line.includes('complete')) return 'success';
  return '';
}

function statusClass(code) {
  if (code >= 200 && code < 300) return 'status-ok';
  return 'status-err';
}

function methodClass(m) {
  return 'method-' + m.toLowerCase();
}

function formatDuration(ms) {
  if (ms < 1000) return ms.toFixed(0) + 'ms';
  return (ms / 1000).toFixed(1) + 's';
}

async function refresh() {
  try {
    // Fetch status and API logs in parallel
    const [statusResp, apiLogResp] = await Promise.all([
      fetch('/api/status'),
      fetch('/api/logs')
    ]);
    const d = await statusResp.json();
    const apiLogs = await apiLogResp.json();

    // Header cards
    const running = d.running;
    document.getElementById('pipeline-status').innerHTML =
      `<span class="status-dot ${running ? 'dot-green' : 'dot-red'}"></span>${running ? 'Running' : 'Stopped'}`;
    document.getElementById('pipeline-status').className = 'card-value ' + (running ? 'green' : 'red');
    document.getElementById('progress').textContent = d.progress_pct + '%';
    document.getElementById('pages-done').textContent = d.done_pages + '/' + d.total_pages;
    document.getElementById('modules-done').textContent = d.done_modules + '/' + d.total_modules;
    document.getElementById('updated').textContent = 'Updated: ' + new Date().toLocaleTimeString();

    // RAG status
    try {
      const rr = await fetch('/api/status-rag');
      const rd = await rr.json();
      document.getElementById('rag-chunks').textContent = rd.error ? 'Error' : (rd.indexed_chunks || 0).toLocaleString();
    } catch(e2) {
      document.getElementById('rag-chunks').textContent = '—';
    }

    // Modules (compact)
    const list = document.getElementById('modules-list');
    const doneCount = d.modules.filter(m => m.status === 'done').length;
    document.getElementById('modules-summary').textContent = `${doneCount}/${d.modules.length} done`;
    list.innerHTML = d.modules.map(m => {
      const pct = m.total ? Math.round(m.completed / m.total * 100) : 0;
      const color = m.status === 'done' ? '#4ade80' :
                    m.status === 'generating' ? '#60a5fa' :
                    m.status === 'failed' ? '#f87171' : '#374151';
      const current = m.current_page ? ` → ${m.current_page}` : '';
      return `<div class="module-row">
        <span class="module-name">${m.name}${current}</span>
        <span class="module-counts">${m.completed}/${m.total}${m.failed ? ' <span style=color:#f87171>' + m.failed + '✗</span>' : ''}</span>
        <div class="module-bar"><div class="module-bar-fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="module-pct">${pct}%</span>
        <span class="badge badge-${m.status}">${m.status}</span>
      </div>`;
    }).join('');

    // API Request Logs (newest first)
    const apiLogBody = document.getElementById('api-log-body');
    const wasAtBottomApi = apiLogBody.scrollHeight - apiLogBody.clientHeight <= apiLogBody.scrollTop + 10;
    document.getElementById('api-log-count').textContent = apiLogs.length + ' requests';
    document.getElementById('api-log-tbody').innerHTML = apiLogs.reverse().map(l =>
      `<tr>
        <td style="color:#6b7280">${l.time}</td>
        <td><span class="method-badge ${methodClass(l.method)}">${l.method}</span></td>
        <td>${l.path}</td>
        <td class="${statusClass(l.status)}">${l.status}</td>
        <td style="color:#6b7280">${formatDuration(l.duration_ms)}</td>
        <td style="color:#9ca3af;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${l.detail || ''}</td>
      </tr>`
    ).join('');
    if (wasAtBottomApi) apiLogBody.scrollTop = apiLogBody.scrollHeight;

    // Pipeline Logs
    const logsEl = document.getElementById('logs-body');
    const wasAtBottom = logsEl.scrollHeight - logsEl.clientHeight <= logsEl.scrollTop + 10;
    logsEl.innerHTML = d.logs.map(l =>
      `<div class="log-line ${pipelineLogClass(l)}">${l}</div>`
    ).join('');
    if (wasAtBottom) logsEl.scrollTop = logsEl.scrollHeight;
    document.getElementById('log-updated').textContent = new Date().toLocaleTimeString();

  } catch(e) { console.error(e); }
}

async function sendQuery() {
  const input = document.getElementById('q-input');
  const btn = document.getElementById('btn-send');
  const resultEl = document.getElementById('q-result');
  const metaEl = document.getElementById('q-meta');
  const query = input.value.trim();
  if (!query) return;

  const endpoint = document.querySelector('input[name="q-endpoint"]:checked').value;
  const fmt = document.querySelector('input[name="q-format"]:checked').value || null;
  const topK = parseInt(document.getElementById('q-topk').value) || 10;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Sending…';
  resultEl.value = '';
  metaEl.textContent = '';

  const t0 = performance.now();
  try {
    let resp;
    if (endpoint === 'ask') {
      resp = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: topK, format: fmt })
      });
    } else {
      resp = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: topK, format: fmt })
      });
    }
    const elapsed = ((performance.now() - t0) / 1000).toFixed(2);

    if (!resp.ok) {
      resultEl.value = 'Error ' + resp.status + ': ' + await resp.text();
      metaEl.textContent = `Failed in ${elapsed}s`;
      return;
    }

    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('text/') || fmt) {
      const text = await resp.text();
      resultEl.value = text;
      const fmtLabel = fmt === 'human' ? 'Human-readable' : 'Markdown';
      metaEl.textContent = `${endpoint.toUpperCase()} · ${elapsed}s · ${fmtLabel} response`;
    } else {
      const data = await resp.json();
      resultEl.value = JSON.stringify(data, null, 2);
      const info = endpoint === 'ask'
        ? `model: ${data.model} · sources: ${data.total_sources}`
        : `results: ${data.total_results}`;
      metaEl.textContent = `${endpoint.toUpperCase()} · ${elapsed}s · ${info}`;
    }
  } catch(e) {
    const elapsed = ((performance.now() - t0) / 1000).toFixed(2);
    resultEl.value = 'Request failed: ' + e.message;
    metaEl.textContent = `Failed in ${elapsed}s`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Send';
  }
}

function copyResult() {
  const text = document.getElementById('q-result').value;
  if (!text) return;
  _copyText(text, document.getElementById('btn-copy-result'), '✓ Copied', '📋 Copy');
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)
