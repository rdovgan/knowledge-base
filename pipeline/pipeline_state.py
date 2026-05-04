"""
Pipeline State Manager — replaces task-master CLI dependency.

Single JSON file tracks all modules and their page tasks.
No external CLI needed. Thread-safe with file locking.

State format:
{
  "version": 1,
  "created_at": "...",
  "updated_at": "...",
  "modules": [
    {
      "name": "redis",
      "description": "...",
      "source_path": "/home/r.dovgan/mbp-rag/redis",
      "output_path": "/home/r.dovgan/cakb/rag/redis",
      "status": "pending|exploring|generating|done|failed",
      "priority": 1,
      "pages": [
        {
          "id": "redis/overview",
          "name": "overview",
          "wiki_filename": "overview.md",
          "status": "pending|generating|done|failed",
          "type": "generate",  # generate | review
          "files": [...],
          "is_overview": true,
          "attempts": 0,
          "score": null,
          "error": null,
          "started_at": null,
          "completed_at": null,
        }
      ],
      "explored_at": null,
      "completed_at": null,
    }
  ]
}
"""

import json
import fcntl
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

STATE_FILE = Path("/home/r.dovgan/cakb/pipeline_state.json")


def _now() -> str:
    return datetime.now().isoformat()


def _read() -> dict:
    """Read state file with locking."""
    if not STATE_FILE.exists():
        return {"version": 1, "created_at": _now(), "updated_at": _now(), "modules": []}
    with open(STATE_FILE) as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        data = json.load(f)
        fcntl.flock(f, fcntl.LOCK_UN)
    return data


def _write(data: dict):
    """Write state file with locking."""
    data["updated_at"] = _now()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2, ensure_ascii=False)
        fcntl.flock(f, fcntl.LOCK_UN)


def state_exists() -> bool:
    return STATE_FILE.exists()


def reset_state():
    """Delete state file to start fresh."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("Pipeline state reset")


def get_full_state() -> dict:
    """Return the entire state (for dashboard)."""
    return _read()


def get_summary() -> dict:
    """Return human-readable summary of all modules and their pages."""
    state = _read()
    modules = []
    for m in state.get("modules", []):
        pages = m.get("pages", [])
        done = [p for p in pages if p["status"] == "done"]
        failed = [p for p in pages if p["status"] == "failed"]
        pending = [p for p in pages if p["status"] == "pending"]
        generating = [p for p in pages if p["status"] == "generating"]
        modules.append({
            "name": m["name"],
            "status": m["status"],
            "total_pages": len(pages),
            "done": len(done),
            "failed": len(failed),
            "pending": len(pending),
            "generating": len(generating),
            "done_pages": [p["name"] for p in done],
            "failed_pages": [p["name"] for p in failed],
            "pending_pages": [p["name"] for p in pending],
            "current_page": generating[0]["name"] if generating else None,
        })
    return {
        "total_modules": len(modules),
        "modules": modules,
        "updated_at": state.get("updated_at", ""),
    }


# ── Module operations ──────────────────────────────────────────────

def init_modules(module_configs: list[dict]):
    """
    Initialize state from modules.yaml config.
    Creates module entries with status=pending and empty pages.
    Idempotent — skips modules that already exist in state.
    """
    state = _read()
    existing = {m["name"] for m in state.get("modules", [])}

    for cfg in module_configs:
        name = cfg["name"]
        if name in existing:
            log.info(f"Module {name} already in state, skipping")
            continue

        module = {
            "name": name,
            "description": cfg.get("description", ""),
            "source_path": f"/home/r.dovgan/mbp-rag/{name}",
            "output_path": f"/home/r.dovgan/cakb/rag/{name}",
            "status": "pending",
            "priority": cfg.get("priority", 99),
            "pages": [],
            "explored_at": None,
            "completed_at": None,
        }
        state.setdefault("modules", []).append(module)
        log.info(f"Initialized module: {name}")

    # Sort by priority
    state["modules"].sort(key=lambda m: m.get("priority", 99))
    _write(state)


def get_next_module_to_explore() -> Optional[dict]:
    """Find the first module with status='pending' (needs exploration)."""
    state = _read()
    for m in state.get("modules", []):
        if m["status"] == "pending":
            return m
    return None


def get_next_page_to_generate() -> Optional[dict]:
    """
    Find the next page that needs generation.
    Looks through modules in order: first module with pending pages.
    Returns {module_name, output_path, page} or None.
    """
    state = _read()
    for m in state.get("modules", []):
        if m["status"] in ("pending", "exploring", "generating", "failed"):
            for p in m.get("pages", []):
                if p["status"] == "pending":
                    return {
                        "module_name": m["name"],
                        "output_path": m["output_path"],
                        "page": p,
                    }
    return None


def get_module(name: str) -> Optional[dict]:
    state = _read()
    for m in state.get("modules", []):
        if m["name"] == name:
            return m
    return None


def set_module_status(name: str, status: str):
    """Update module status."""
    state = _read()
    for m in state.get("modules", []):
        if m["name"] == name:
            m["status"] = status
            if status == "exploring":
                m["explored_at"] = _now()
            elif status == "done":
                m["completed_at"] = _now()
            _write(state)
            log.info(f"Module {name} → {status}")
            return
    log.error(f"Module {name} not found")


def set_pages_for_module(name: str, pages: list[dict]):
    """
    Set the pages list for a module after exploration.
    Replaces any existing pages.
    """
    state = _read()
    for m in state.get("modules", []):
        if m["name"] == name:
            m["pages"] = pages
            m["status"] = "generating" if pages else "done"
            _write(state)
            log.info(f"Module {name}: set {len(pages)} pages")
            return
    log.error(f"Module {name} not found")


def set_page_status(module_name: str, page_name: str, status: str,
                    score: float = None, error: str = None):
    """Update a specific page's status."""
    state = _read()
    for m in state.get("modules", []):
        if m["name"] == module_name:
            for p in m.get("pages", []):
                if p["name"] == page_name:
                    p["status"] = status
                    if status == "generating":
                        p["started_at"] = _now()
                        p["attempts"] = p.get("attempts", 0) + 1
                    elif status == "done":
                        p["completed_at"] = _now()
                        if score is not None:
                            p["score"] = score
                    elif status == "failed":
                        p["completed_at"] = _now()
                        p["error"] = error
                    _write(state)
                    log.info(f"Page {module_name}/{page_name} → {status}")
                    return
    log.error(f"Page {module_name}/{page_name} not found")


def check_module_complete(module_name: str) -> bool:
    """Check if all pages are done/failed, update module status."""
    state = _read()
    for m in state.get("modules", []):
        if m["name"] == module_name:
            pages = m.get("pages", [])
            if not pages:
                return False
            all_resolved = all(p["status"] in ("done", "failed") for p in pages)
            if all_resolved:
                m["status"] = "done"
                m["completed_at"] = _now()
                _write(state)
                done_count = sum(1 for p in pages if p["status"] == "done")
                fail_count = sum(1 for p in pages if p["status"] == "failed")
                log.info(f"Module {module_name} complete: "
                         f"{done_count} done, {fail_count} failed")
                return True
            return False
    return False


def get_stats() -> dict:
    """Global statistics for dashboard."""
    state = _read()
    total_modules = 0
    done_modules = 0
    total_pages = 0
    done_pages = 0
    failed_pages = 0
    pending_pages = 0

    for m in state.get("modules", []):
        total_modules += 1
        if m["status"] == "done":
            done_modules += 1
        for p in m.get("pages", []):
            total_pages += 1
            if p["status"] == "done":
                done_pages += 1
            elif p["status"] == "failed":
                failed_pages += 1
            elif p["status"] == "pending":
                pending_pages += 1

    return {
        "total_modules": total_modules,
        "done_modules": done_modules,
        "total_pages": total_pages,
        "done_pages": done_pages,
        "failed_pages": failed_pages,
        "pending_pages": pending_pages,
        "progress_pct": round(done_pages / total_pages * 100, 1) if total_pages else 0,
    }


def is_pipeline_complete() -> bool:
    """Check if all modules are done."""
    state = _read()
    for m in state.get("modules", []):
        if m["status"] not in ("done", "failed"):
            return False
    return True
