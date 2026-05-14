"""
SQLite database for persistent API request/response history.
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DB_DIR / "api_history.db"

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Thread-local DB connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn


def init_db():
    """Create tables if not exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS api_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            method TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            query_text TEXT DEFAULT '',
            status_code INTEGER DEFAULT 0,
            duration_ms REAL DEFAULT 0,
            request_params TEXT DEFAULT '{}',
            response_body TEXT DEFAULT '',
            response_format TEXT DEFAULT '',
            model_used TEXT DEFAULT '',
            sources_count INTEGER DEFAULT 0,
            error TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_requests_created
            ON api_requests(created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_requests_endpoint
            ON api_requests(endpoint);

        CREATE INDEX IF NOT EXISTS idx_requests_query
            ON api_requests(query_text);
    """)
    conn.commit()


def insert_request(
    method: str,
    endpoint: str,
    query_text: str = "",
    status_code: int = 0,
    duration_ms: float = 0,
    request_params: dict = None,
    response_body: str = "",
    response_format: str = "",
    model_used: str = "",
    sources_count: int = 0,
    error: str = "",
) -> int:
    """Insert a request record and return its ID."""
    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO api_requests
           (created_at, method, endpoint, query_text, status_code, duration_ms,
            request_params, response_body, response_format, model_used,
            sources_count, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            method,
            endpoint,
            query_text[:500],
            status_code,
            round(duration_ms, 1),
            json.dumps(request_params or {}, ensure_ascii=False),
            response_body,
            response_format,
            model_used,
            sources_count,
            error[:1000],
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_history(
    page: int = 1,
    per_page: int = 20,
    endpoint: Optional[str] = None,
    q: Optional[str] = None,
    method: Optional[str] = None,
    status: Optional[int] = None,
) -> dict:
    """Paginated history with optional filters."""
    conn = _get_conn()
    where_parts = []
    params = []

    if endpoint:
        where_parts.append("endpoint = ?")
        params.append(endpoint)
    if q:
        where_parts.append("query_text LIKE ?")
        params.append(f"%{q}%")
    if method:
        where_parts.append("method = ?")
        params.append(method.upper())
    if status is not None:
        where_parts.append("status_code = ?")
        params.append(status)

    where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # Total count
    total = conn.execute(f"SELECT COUNT(*) FROM api_requests{where}", params).fetchone()[0]

    # Page
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"""SELECT id, created_at, method, endpoint, query_text,
                   status_code, duration_ms, model_used, sources_count, error
            FROM api_requests{where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    items = [dict(r) for r in rows]
    total_pages = max(1, (total + per_page - 1) // per_page)

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


def get_request_detail(request_id: int) -> Optional[dict]:
    """Get full request detail including response body."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM api_requests WHERE id = ?", (request_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    # Parse request_params back to dict
    try:
        d["request_params"] = json.loads(d.get("request_params", "{}"))
    except (json.JSONDecodeError, TypeError):
        d["request_params"] = {}
    return d


def get_recent_logs(n: int = 200) -> list:
    """Get last N requests (for /api/logs backward compat)."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, created_at, method, endpoint, query_text,
                  status_code, duration_ms, error
           FROM api_requests
           ORDER BY created_at DESC LIMIT ?""",
        (n,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Aggregate stats for dashboard."""
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM api_requests").fetchone()[0]
    except Exception:
        total = 0

    try:
        today = conn.execute(
            "SELECT COUNT(*) FROM api_requests WHERE date(created_at) = date('now')"
        ).fetchone()[0]
    except Exception:
        today = 0

    try:
        avg_ms = conn.execute(
            "SELECT ROUND(AVG(duration_ms), 0) FROM api_requests WHERE duration_ms > 0"
        ).fetchone()[0] or 0
    except Exception:
        avg_ms = 0

    try:
        by_endpoint = conn.execute(
            "SELECT endpoint, COUNT(*) as cnt FROM api_requests GROUP BY endpoint ORDER BY cnt DESC"
        ).fetchall()
        endpoints = {r["endpoint"]: r["cnt"] for r in by_endpoint}
    except Exception:
        endpoints = {}

    return {
        "total_requests": total,
        "today_requests": today,
        "avg_duration_ms": int(avg_ms),
        "by_endpoint": endpoints,
    }


def prune_old(days: int = 90) -> int:
    """Delete records older than N days. Returns deleted count."""
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    cur = conn.execute("DELETE FROM api_requests WHERE created_at < ?", (cutoff,))
    conn.commit()
    return cur.rowcount


# Initialize on import
init_db()
