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
  GET  /api/history    — Paginated request history (DB-backed)
  GET  /api/history/{id} — Full request/response detail
  GET  /api/stats      — Aggregated API usage stats
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query as QueryParam, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
import logging
import uvicorn
import subprocess
import db as db_module

app = FastAPI(title="CAKB — RAG Pipeline & Query API")

log = logging.getLogger("cakb.api")

# ── DB-backed API request logging via middleware ────────────────

# Paths to skip from logging
_SKIP_LOG_PREFIXES = ("/api/status", "/api/logs", "/api/stats", "/api/history", "/favicon.ico")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware that logs all API requests to SQLite."""
    start = datetime.now()

    # Read request body for POST endpoints
    request_body = {}
    if request.method == "POST":
        try:
            body_bytes = await request.body()
            if body_bytes:
                request_body = json.loads(body_bytes)
        except Exception:
            request_body = {}

    # Call the actual endpoint
    response = await call_next(request)

    # Capture response body from streaming response
    response_body = ""
    try:
        body_parts = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                body_parts.append(chunk)
            elif isinstance(chunk, str):
                body_parts.append(chunk.encode("utf-8"))
            else:
                body_parts.append(str(chunk).encode("utf-8"))
        raw_body = b"".join(body_parts)
        response_body = raw_body.decode("utf-8", errors="replace")
    except Exception:
        raw_body = b""
        response_body = ""

    # Build a clean response to send back to client
    # Avoid copying hop-by-hop headers that cause issues
    skip_headers = {"transfer-encoding", "content-encoding", "content-length"}
    clean_headers = {
        k: v for k, v in response.headers.items()
        if k.lower() not in skip_headers
    }

    new_response = Response(
        content=raw_body,
        status_code=response.status_code,
        headers=clean_headers,
        media_type=response.media_type,
    )

    duration_ms = (datetime.now() - start).total_seconds() * 1000
    path = request.url.path

    # Only log real API calls (skip status polling, logs, etc.)
    if path.startswith("/api/") and not any(path.startswith(p) for p in _SKIP_LOG_PREFIXES):
        try:
            query_text = request_body.get("query", "") or dict(request.query_params).get("q", "")
            fmt = request_body.get("format", "") or dict(request.query_params).get("format", "")
            model_used = ""
            sources_count = 0
            error_msg = ""

            # Try to extract model/sources from JSON response
            if response_body:
                try:
                    resp_json = json.loads(response_body)
                    model_used = resp_json.get("model", "")
                    sources_count = resp_json.get("total_sources", resp_json.get("total_results", 0))
                except (json.JSONDecodeError, TypeError):
                    # Try to extract from Markdown response
                    import re
                    m = re.search(r'\*\*Model:\*\*\s*(.+)', response_body)
                    if m:
                        model_used = m.group(1).strip()
                    m = re.search(r'\*\*Sources used:\*\*\s*(\d+)', response_body)
                    if m:
                        sources_count = int(m.group(1))
                    m = re.search(r'\*\*Results:\*\*\s*(\d+)', response_body)
                    if m:
                        sources_count = int(m.group(1))

            if response.status_code >= 400:
                error_msg = response_body[:1000] if response_body else ""

            # Truncate large response bodies for storage
            stored_body = response_body[:50000] if response_body else ""

            db_module.insert_request(
                method=request.method,
                endpoint=path,
                query_text=query_text,
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_params=request_body,
                response_body=stored_body,
                response_format=fmt,
                model_used=model_used,
                sources_count=sources_count,
                error=error_msg,
            )
        except Exception as e:
            log.warning(f"Failed to log request to DB: {e}")

    return new_response


@app.get("/api/logs")
def api_get_logs():
    """Recent API request log (DB-backed, backward compatible)."""
    return db_module.get_recent_logs(200)


@app.get("/api/stats")
def api_stats():
    """Aggregated API usage stats."""
    return db_module.get_stats()


@app.get("/api/history")
def api_history(
    page: int = QueryParam(1, ge=1),
    per_page: int = QueryParam(20, ge=1, le=100),
    endpoint: Optional[str] = None,
    q: Optional[str] = None,
    method: Optional[str] = None,
    status: Optional[int] = None,
):
    """Paginated request history from DB.

    Example:
        curl 'http://localhost:8090/api/history?page=1&per_page=10&endpoint=/api/ask'
    """
    return db_module.get_history(
        page=page, per_page=per_page,
        endpoint=endpoint, q=q, method=method, status=status,
    )


@app.get("/api/history/{request_id}")
def api_history_detail(request_id: int):
    """Full request/response detail.

    Example:
        curl http://localhost:8090/api/history/42
    """
    detail = db_module.get_request_detail(request_id)
    if not detail:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return detail

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
        if req.format == "md":
            return PlainTextResponse(_format_ask_md(result), media_type="text/markdown")
        if req.format == "human":
            return PlainTextResponse(_humanize_ask(result), media_type="text/markdown")
        return result
    except Exception as e:
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
    return result


@app.get("/api/reset")
def api_reset():
    """Reset pipeline state."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    return {"status": "reset"}


@app.get("/", response_class=HTMLResponse)

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

  /* Tabs */
  .tabs { display: flex; gap: 0; margin-bottom: 24px; border-bottom: 1px solid #2a2d3a; }
  .tab { padding: 10px 20px; cursor: pointer; font-size: 14px; font-weight: 600; color: #6b7280; border-bottom: 2px solid transparent; transition: all .15s; }
  .tab:hover { color: #e0e0e0; }
  .tab.active { color: #60a5fa; border-bottom-color: #2563eb; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }

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
  .row-clickable { cursor: pointer; }
  .row-clickable:hover { background: #1e2130 !important; }

  /* History table */
  .history-filters { display: flex; gap: 10px; align-items: center; padding: 12px 20px; border-bottom: 1px solid #2a2d3a; flex-wrap: wrap; }
  .history-filters input, .history-filters select { background: #0f1117; border: 1px solid #2a2d3a; border-radius: 6px; color: #e0e0e0; padding: 5px 10px; font-size: 12px; outline: none; }
  .history-filters input:focus, .history-filters select:focus { border-color: #2563eb; }
  .history-filters input::placeholder { color: #4b5563; }
  .btn-filter { background: #2563eb; color: #fff; border: none; padding: 5px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; }
  .btn-filter:hover { background: #3b82f6; }
  .pagination { display: flex; justify-content: center; align-items: center; gap: 6px; padding: 12px 20px; border-top: 1px solid #2a2d3a; }
  .page-btn { background: #2a2d3a; color: #9ca3af; border: none; padding: 5px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; }
  .page-btn:hover { background: #3b4252; color: #fff; }
  .page-btn.active { background: #2563eb; color: #fff; }
  .page-btn:disabled { opacity: .3; cursor: not-allowed; }
  .page-info { color: #6b7280; font-size: 12px; padding: 0 12px; }

  /* Detail modal */
  .detail-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1000; justify-content: center; align-items: center; }
  .detail-overlay.active { display: flex; }
  .detail-modal { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 16px; max-width: 900px; width: 90%; max-height: 85vh; overflow-y: auto; }
  .detail-header { padding: 16px 24px; border-bottom: 1px solid #2a2d3a; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; background: #1a1d27; z-index: 1; border-radius: 16px 16px 0 0; }
  .detail-header h3 { font-size: 15px; color: #fff; }
  .detail-close { background: none; border: none; color: #6b7280; font-size: 20px; cursor: pointer; padding: 4px 8px; border-radius: 6px; }
  .detail-close:hover { background: #2a2d3a; color: #fff; }
  .detail-body { padding: 20px 24px; }
  .detail-meta { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 16px; }
  .detail-meta-item { font-size: 12px; }
  .detail-meta-item .label { color: #6b7280; }
  .detail-meta-item .value { color: #e0e0e0; font-weight: 500; }
  .detail-section { margin-bottom: 16px; }
  .detail-section-title { font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
  .detail-code { background: #0f1117; border: 1px solid #2a2d3a; border-radius: 8px; padding: 12px 14px; font-family: 'Menlo','Consolas',monospace; font-size: 12px; color: #e0e0e0; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; line-height: 1.5; }

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

<div class="tabs">
  <div class="tab active" onclick="switchTab('dashboard', this)">📊 Dashboard</div>
  <div class="tab" onclick="switchTab('history', this)">📜 History</div>
</div>

<!-- Tab: Dashboard -->
<div class="tab-content active" id="tab-dashboard">

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
    <span>🔗 Recent API Requests</span>
    <span style="font-size:11px;color:#6b7280" id="api-log-count"></span>
  </div>
  <div class="section-body" style="max-height:300px;overflow-y:auto" id="api-log-body">
    <table class="api-log-table">
      <thead><tr><th>Time</th><th></th><th>Endpoint</th><th>Query</th><th>Status</th><th>Duration</th></tr></thead>
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

</div><!-- /tab-dashboard -->

<!-- Tab: History -->
<div class="tab-content" id="tab-history">
  <div class="section">
    <div class="section-header">
      <span>📜 Request History (Persistent)</span>
      <span style="font-size:11px;color:#6b7280" id="history-total"></span>
    </div>
    <div class="history-filters">
      <input type="text" id="hf-search" placeholder="Search queries…" style="flex:1;min-width:160px" onkeydown="if(event.key==='Enter')loadHistory(1)">
      <select id="hf-endpoint" style="width:140px">
        <option value="">All endpoints</option>
        <option value="/api/ask">/api/ask</option>
        <option value="/api/query">/api/query</option>
      </select>
      <select id="hf-method" style="width:100px">
        <option value="">Any method</option>
        <option value="GET">GET</option>
        <option value="POST">POST</option>
      </select>
      <select id="hf-status" style="width:110px">
        <option value="">Any status</option>
        <option value="200">200 OK</option>
        <option value="500">500 Error</option>
      </select>
      <button class="btn-filter" onclick="loadHistory(1)">Search</button>
    </div>
    <div style="overflow-x:auto">
      <table class="api-log-table">
        <thead><tr>
          <th>ID</th><th>Time</th><th></th><th>Endpoint</th><th>Query</th>
          <th>Status</th><th>Duration</th><th>Model</th><th>Sources</th>
        </tr></thead>
        <tbody id="history-tbody"></tbody>
      </table>
    </div>
    <div class="pagination" id="history-pagination"></div>
  </div>
</div><!-- /tab-history -->

<!-- Detail Modal -->
<div class="detail-overlay" id="detail-modal" onclick="if(event.target===this)closeDetail()">
  <div class="detail-modal">
    <div class="detail-header">
      <h3 id="detail-title">Request Detail</h3>
      <button class="detail-close" onclick="closeDetail()">✕</button>
    </div>
    <div class="detail-body" id="detail-body">Loading...</div>
  </div>
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
          <tr><td>format</td><td>string, optional — "md" or "human" for Markdown</td></tr>
        </table>
      </div>

      <div class="api-section">
        <h3>GET /api/history — Paginated Request History</h3>
        <p>Browse all past API requests stored in SQLite. Filter by endpoint, method, status, or search queries.</p>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl 'http://localhost:8090/api/history?page=1&per_page=10&endpoint=/api/ask'</div>
        <table class="param-table">
          <tr><td>page</td><td>int, default 1 — Page number</td></tr>
          <tr><td>per_page</td><td>int, default 20 — Items per page (max 100)</td></tr>
          <tr><td>endpoint</td><td>string, optional — Filter by endpoint path</td></tr>
          <tr><td>q</td><td>string, optional — Search in query text</td></tr>
          <tr><td>method</td><td>string, optional — Filter by HTTP method</td></tr>
          <tr><td>status</td><td>int, optional — Filter by status code</td></tr>
        </table>
      </div>

      <div class="api-section">
        <h3>GET /api/history/{id} — Full Request/Response Detail</h3>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl http://localhost:8090/api/history/42</div>
      </div>

      <div class="api-section">
        <h3>GET /api/stats — API Usage Stats</h3>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl http://localhost:8090/api/stats</div>
      </div>

      <div class="api-section" style="margin-bottom:0">
        <h3>GET /api/logs — Recent Request Log</h3>
        <div class="code-block"><button class="btn-copy" onclick="copyCode(this)">Copy</button>curl http://localhost:8090/api/logs</div>
      </div>

    </div>
  </div>
</div>

<script>
// ── Tab switching ───────────────────────────────────────────────
function switchTab(tab, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  if (el) el.classList.add('active');
  if (tab === 'history') loadHistory(1);
}

function toggleModal(show) {
  document.getElementById('help-modal').classList.toggle('active', show);
}

function _copyText(text, btn, okLabel, origLabel) {
  try { navigator.clipboard.writeText(text).then(() => { btn.textContent = okLabel; setTimeout(() => btn.textContent = origLabel, 1500); }); }
  catch(e) { const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta); btn.textContent = okLabel; setTimeout(() => btn.textContent = origLabel, 1500); }
}

function copyCode(btn) {
  const clone = btn.parentElement.cloneNode(true);
  clone.querySelector('.btn-copy')?.remove();
  _copyText(clone.textContent.trim(), btn, '✓', 'Copy');
}

function pipelineLogClass(line) {
  if (line.includes('ERROR') || line.includes('❌')) return 'error';
  if (line.includes('WARNING') || line.includes('⚠')) return 'warning';
  if (line.includes('✅') || line.includes('complete')) return 'success';
  return '';
}

function statusClass(code) { return (code >= 200 && code < 300) ? 'status-ok' : 'status-err'; }
function methodClass(m) { return 'method-' + m.toLowerCase(); }
function formatDuration(ms) { if (!ms) return '—'; return ms < 1000 ? ms.toFixed(0) + 'ms' : (ms / 1000).toFixed(1) + 's'; }
function formatTime(iso) { if (!iso) return '—'; try { return new Date(iso).toLocaleString(); } catch(e) { return iso; } }
function esc(s) { if (!s) return ''; return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── Dashboard refresh ───────────────────────────────────────────
async function refresh() {
  try {
    const [statusResp, apiLogResp] = await Promise.all([
      fetch('/api/status'),
      fetch('/api/logs')
    ]);
    const d = await statusResp.json();
    const apiLogs = await apiLogResp.json();

    document.getElementById('updated').textContent = 'Updated: ' + new Date().toLocaleTimeString();

    // Modules
    const list = document.getElementById('modules-list');
    const doneCount = d.modules.filter(m => m.status === 'done').length;
    document.getElementById('modules-summary').textContent = `${doneCount}/${d.modules.length} done`;
    list.innerHTML = d.modules.map(m => {
      const pct = m.total ? Math.round(m.completed / m.total * 100) : 0;
      const color = m.status === 'done' ? '#4ade80' : m.status === 'generating' ? '#60a5fa' : m.status === 'failed' ? '#f87171' : '#374151';
      const current = m.current_page ? ` → ${m.current_page}` : '';
      return `<div class="module-row">
        <span class="module-name">${m.name}${current}</span>
        <span class="module-counts">${m.completed}/${m.total}${m.failed ? ' <span style=color:#f87171>' + m.failed + '✗</span>' : ''}</span>
        <div class="module-bar"><div class="module-bar-fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="module-pct">${pct}%</span>
        <span class="badge badge-${m.status}">${m.status}</span>
      </div>`;
    }).join('');

    // Recent API Requests (clickable rows)
    const apiLogBody = document.getElementById('api-log-body');
    const wasAtBottomApi = apiLogBody.scrollHeight - apiLogBody.clientHeight <= apiLogBody.scrollTop + 10;
    document.getElementById('api-log-count').textContent = apiLogs.length + ' requests';
    document.getElementById('api-log-tbody').innerHTML = apiLogs.map(l =>
      `<tr class="row-clickable" onclick="showDetail(${l.id})">
        <td style="color:#6b7280;white-space:nowrap">${formatTime(l.created_at)}</td>
        <td><span class="method-badge ${methodClass(l.method)}">${l.method}</span></td>
        <td>${l.endpoint}</td>
        <td style="color:#9ca3af;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(l.query_text || l.error || '')}</td>
        <td class="${statusClass(l.status_code)}">${l.status_code}</td>
        <td style="color:#6b7280">${formatDuration(l.duration_ms)}</td>
      </tr>`
    ).join('');
    if (wasAtBottomApi) apiLogBody.scrollTop = apiLogBody.scrollHeight;

    // Pipeline Logs
    const logsEl = document.getElementById('logs-body');
    const wasAtBottom = logsEl.scrollHeight - logsEl.clientHeight <= logsEl.scrollTop + 10;
    logsEl.innerHTML = d.logs.map(l => `<div class="log-line ${pipelineLogClass(l)}">${l}</div>`).join('');
    if (wasAtBottom) logsEl.scrollTop = logsEl.scrollHeight;
    document.getElementById('log-updated').textContent = new Date().toLocaleTimeString();
  } catch(e) { console.error(e); }
}

// ── History tab ─────────────────────────────────────────────────
async function loadHistory(page) {
  const search = document.getElementById('hf-search').value.trim();
  const endpoint = document.getElementById('hf-endpoint').value;
  const method = document.getElementById('hf-method').value;
  const status = document.getElementById('hf-status').value;

  const params = new URLSearchParams({page, per_page: 15});
  if (search) params.set('q', search);
  if (endpoint) params.set('endpoint', endpoint);
  if (method) params.set('method', method);
  if (status) params.set('status', status);

  try {
    const resp = await fetch('/api/history?' + params);
    const data = await resp.json();

    document.getElementById('history-total').textContent = `${data.total} total`;

    document.getElementById('history-tbody').innerHTML = data.items.map(r =>
      `<tr class="row-clickable" onclick="showDetail(${r.id})">
        <td style="color:#6b7280">${r.id}</td>
        <td style="color:#6b7280;white-space:nowrap">${formatTime(r.created_at)}</td>
        <td><span class="method-badge ${methodClass(r.method)}">${r.method}</span></td>
        <td>${r.endpoint}</td>
        <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.query_text)}</td>
        <td class="${statusClass(r.status_code)}">${r.status_code}</td>
        <td style="color:#6b7280;white-space:nowrap">${formatDuration(r.duration_ms)}</td>
        <td style="color:#60a5fa;font-size:11px">${r.model_used || '—'}</td>
        <td style="color:#6b7280">${r.sources_count || '—'}</td>
      </tr>`
    ).join('');

    // Pagination
    const totalPages = data.total_pages;
    let pagHtml = `<button class="page-btn" ${page <= 1 ? 'disabled' : ''} onclick="loadHistory(${page - 1})">← Prev</button>`;
    const startP = Math.max(1, page - 3);
    const endP = Math.min(totalPages, page + 3);
    for (let p = startP; p <= endP; p++) {
      pagHtml += `<button class="page-btn ${p === page ? 'active' : ''}" onclick="loadHistory(${p})">${p}</button>`;
    }
    pagHtml += `<button class="page-btn" ${page >= totalPages ? 'disabled' : ''} onclick="loadHistory(${page + 1})">Next →</button>`;
    pagHtml += `<span class="page-info">Page ${page} of ${totalPages}</span>`;
    document.getElementById('history-pagination').innerHTML = pagHtml;
  } catch(e) { console.error('History load error:', e); }
}

// ── Detail modal ────────────────────────────────────────────────
async function showDetail(id) {
  document.getElementById('detail-modal').classList.add('active');
  document.getElementById('detail-body').innerHTML = '<div style="padding:40px;text-align:center;color:#6b7280">Loading…</div>';

  try {
    const resp = await fetch('/api/history/' + id);
    const d = await resp.json();

    document.getElementById('detail-title').textContent = `${d.method} ${d.endpoint} — #${d.id}`;

    let html = `<div class="detail-meta">
      <div class="detail-meta-item"><div class="label">Time</div><div class="value">${formatTime(d.created_at)}</div></div>
      <div class="detail-meta-item"><div class="label">Status</div><div class="value ${statusClass(d.status_code)}">${d.status_code}</div></div>
      <div class="detail-meta-item"><div class="label">Duration</div><div class="value">${formatDuration(d.duration_ms)}</div></div>
      <div class="detail-meta-item"><div class="label">Model</div><div class="value">${d.model_used || '—'}</div></div>
      <div class="detail-meta-item"><div class="label">Sources</div><div class="value">${d.sources_count}</div></div>
      <div class="detail-meta-item"><div class="label">Format</div><div class="value">${d.response_format || 'json'}</div></div>
    </div>`;

    if (d.query_text) {
      html += `<div class="detail-section"><div class="detail-section-title">Query</div><div class="detail-code">${esc(d.query_text)}</div></div>`;
    }

    if (d.request_params && Object.keys(d.request_params).length > 0) {
      html += `<div class="detail-section"><div class="detail-section-title">Request Parameters</div><div class="detail-code">${esc(JSON.stringify(d.request_params, null, 2))}</div></div>`;
    }

    if (d.error) {
      html += `<div class="detail-section"><div class="detail-section-title" style="color:#f87171">Error</div><div class="detail-code" style="border-color:#450a0a">${esc(d.error)}</div></div>`;
    }

    if (d.response_body) {
      let displayBody = d.response_body;
      let label = d.response_format ? '(' + d.response_format + ')' : '';
      try { const p = JSON.parse(d.response_body); displayBody = JSON.stringify(p, null, 2); label = '(JSON)'; } catch(e) {}
      html += `<div class="detail-section"><div class="detail-section-title">Response Body ${label}</div><div class="detail-code" style="max-height:500px">${esc(displayBody)}</div></div>`;
    }

    document.getElementById('detail-body').innerHTML = html;
  } catch(e) {
    document.getElementById('detail-body').innerHTML = `<div style="padding:20px;color:#f87171">Error: ${e.message}</div>`;
  }
}

function closeDetail() {
  document.getElementById('detail-modal').classList.remove('active');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeDetail(); toggleModal(false); }
});

// ── Query form ──────────────────────────────────────────────────
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
    const resp = await fetch('/api/' + endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: topK, format: fmt })
    });
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
      metaEl.textContent = `${endpoint.toUpperCase()} · ${elapsed}s · ${fmt === 'human' ? 'Human-readable' : 'Markdown'}`;
    } else {
      const data = await resp.json();
      resultEl.value = JSON.stringify(data, null, 2);
      const info = endpoint === 'ask' ? `model: ${data.model} · sources: ${data.total_sources}` : `results: ${data.total_results}`;
      metaEl.textContent = `${endpoint.toUpperCase()} · ${elapsed}s · ${info}`;
    }
  } catch(e) {
    resultEl.value = 'Request failed: ' + e.message;
    metaEl.textContent = `Failed in ${((performance.now() - t0) / 1000).toFixed(2)}s`;
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
