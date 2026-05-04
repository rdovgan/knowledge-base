"""
Taskmaster client — Python wrapper for Taskmaster CLI and direct tasks.json manipulation.

Uses Taskmaster CLI for status queries/updates, and direct JSON manipulation
for creating structured subtasks with custom metadata (type, module, source_path, etc.).
"""

import json
import os
import subprocess
import logging
import fcntl
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

TASKS_FILE = Path("/home/r.dovgan/cakb/.taskmaster/tasks/tasks.json")
TAG = "pipeline"
PROJECT_ROOT = "/home/r.dovgan/cakb"


def _normalize_priority(val) -> str:
    """Convert priority to Taskmaster format (high/medium/low)."""
    if isinstance(val, int):
        return "high" if val <= 3 else "medium" if val <= 7 else "low"
    if isinstance(val, str):
        return val.lower()
    return "medium"


def _run_cli(args: list, silent: bool = False) -> subprocess.CompletedProcess:
    """Run a task-master CLI command."""
    cmd = [os.path.expanduser("~/.nvm/versions/node/v20.20.2/bin/task-master")] + args + ["-p", PROJECT_ROOT]
    if silent:
        cmd.append("--silent")
    return subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)


def _read_tasks() -> dict:
    """Read the raw tasks.json file."""
    if not TASKS_FILE.exists():
        return {}
    with open(TASKS_FILE) as f:
        return json.load(f)


def _write_tasks(data: dict):
    """Write the raw tasks.json file with file locking."""
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2)
        fcntl.flock(f, fcntl.LOCK_UN)


def _get_tag_tasks() -> list:
    """Get the list of tasks for our tag."""
    data = _read_tasks()
    return data.get(TAG, {}).get("tasks", [])


def _set_tag_tasks(tasks: list):
    """Set the list of tasks for our tag."""
    data = _read_tasks()
    if TAG not in data:
        data[TAG] = {"tasks": [], "metadata": {}}
    data[TAG]["tasks"] = tasks
    from datetime import datetime
    data[TAG]["metadata"]["updated"] = datetime.now().isoformat()
    _write_tasks(data)


def _next_id(tasks: list) -> int:
    """Get the next available task ID."""
    if not tasks:
        return 1
    max_id = max(t["id"] for t in tasks)
    max_sub = 0
    for t in tasks:
        if t.get("subtasks"):
            sub_max = max(s["id"] for s in t["subtasks"])
            max_sub = max(max_sub, sub_max)
    return max(max_id, max_sub) + 1


def get_next_task() -> Optional[dict]:
    """
    Get the next pending task (with unmet dependencies resolved).
    Uses `task-master next --format json` CLI command.
    Returns task dict or None if no tasks available.
    """
    result = _run_cli(["next", "--format", "json"])
    try:
        # Strip telemetry/status lines before JSON
        lines = result.stdout.strip().split('\n')
        json_start = None
        for i, line in enumerate(lines):
            if line.startswith('{'):
                json_start = i
                break
        if json_start is None:
            return None
        data = json.loads('\n'.join(lines[json_start:]))
        if data.get("found"):
            task = data["task"]
            # Enrich with metadata from our tasks.json
            task_id = str(task["id"])
            enriched = _enrich_task(task, task_id)
            return enriched
        return None
    except (json.JSONDecodeError, KeyError) as e:
        log.warning(f"Failed to parse task-master next output: {e}")
        return None


def _enrich_task(task: dict, task_id: str) -> dict:
    """Enrich a task with our custom metadata from tasks.json."""
    tasks = _get_tag_tasks()
    for t in tasks:
        if str(t["id"]) == task_id:
            # Copy custom metadata fields
            for key in ("type", "module", "source_path", "output_path",
                        "wiki_filename", "file_list", "is_overview"):
                if key in t:
                    task[key] = t[key]
            break
        # Check subtasks
        if t.get("subtasks"):
            for s in t["subtasks"]:
                if str(s["id"]) == task_id:
                    for key in ("type", "module", "source_path", "output_path",
                                "wiki_filename", "file_list", "is_overview"):
                        if key in s:
                            task[key] = s[key]
                    # Also store parent info
                    task["parent_id"] = t["id"]
                    break
    return task


def set_status(task_id: str, status: str) -> bool:
    """
    Update task status. Uses Taskmaster CLI.
    Status: pending | in-progress | done | failed | deferred | cancelled | review
    """
    result = _run_cli(["set-status", str(task_id), status], silent=True)
    if result.returncode != 0:
        log.error(f"Failed to set status for task {task_id}: {result.stderr}")
        return False
    log.info(f"Task {task_id} status set to {status}")
    return True


def set_subtask_status(parent_id: int, subtask_id: int, status: str) -> bool:
    """
    Update a subtask's status directly in tasks.json.
    Subtask IDs in Taskmaster are like "1.1" but we store them as integers.
    """
    tasks = _get_tag_tasks()
    for t in tasks:
        if t["id"] == parent_id:
            for s in t.get("subtasks", []):
                if s["id"] == subtask_id:
                    s["status"] = status
                    _set_tag_tasks(tasks)
                    log.info(f"Subtask {parent_id}.{subtask_id} status set to {status}")
                    return True
    log.error(f"Subtask {parent_id}.{subtask_id} not found")
    return False


def create_parent_task(module: dict) -> int:
    """
    Create a parent task for a module. Returns the task ID.
    """
    tasks = _get_tag_tasks()
    new_id = _next_id(tasks)
    task = {
        "id": new_id,
        "title": f"Process module: {module['name']}",
        "description": module.get('description', ''),
        "details": f"Source: /home/r.dovgan/mbp-rag/{module['name']}\n"
                   f"Output: /home/r.dovgan/cakb/rag/{module['name']}",
        "testStrategy": "",
        "status": "pending",
        "dependencies": [],
        "priority": _normalize_priority(module.get('priority', 'medium')),
        "subtasks": [],
        # Custom metadata
        "type": "module",
        "module": module['name'],
        "source_path": f"/home/r.dovgan/mbp-rag/{module['name']}",
        "output_path": f"/home/r.dovgan/cakb/rag/{module['name']}",
    }
    tasks.append(task)
    _set_tag_tasks(tasks)
    log.info(f"Created parent task {new_id} for module {module['name']}")
    return new_id


def create_explorer_subtask(parent_id: int, module_name: str) -> int:
    """
    Create an 'explore' subtask under a parent task.
    """
    tasks = _get_tag_tasks()
    parent = next((t for t in tasks if t["id"] == parent_id), None)
    if not parent:
        log.error(f"Parent task {parent_id} not found")
        return -1

    subtasks = parent.get("subtasks", [])
    sub_id = 1
    if subtasks:
        sub_id = max(s["id"] for s in subtasks) + 1

    subtask = {
        "id": sub_id,
        "title": f"Explore {module_name}",
        "description": f"Analyze source code structure and identify domains for {module_name}",
        "details": "",
        "status": "pending",
        "dependencies": [],
        # Custom metadata
        "type": "explore",
        "module": module_name,
        "source_path": f"/home/r.dovgan/mbp-rag/{module_name}",
        "output_path": f"/home/r.dovgan/cakb/rag/{module_name}",
    }
    parent.setdefault("subtasks", []).append(subtask)
    _set_tag_tasks(tasks)
    log.info(f"Created explore subtask {parent_id}.{sub_id} for {module_name}")
    return sub_id


def create_generate_review_subtasks(
    parent_id: int,
    module_name: str,
    page_name: str,
    wiki_filename: str,
    file_list: list,
    depends_on_subtask: Optional[int] = None,
    is_overview: bool = False,
) -> tuple:
    """
    Create a pair of generate + review subtasks for a wiki page.
    Returns (generate_subtask_id, review_subtask_id).

    The review subtask depends on the generate subtask.
    If depends_on_subtask is given, generate depends on that (e.g., explore subtask or previous review).
    """
    tasks = _get_tag_tasks()
    parent = next((t for t in tasks if t["id"] == parent_id), None)
    if not parent:
        log.error(f"Parent task {parent_id} not found")
        return -1, -1

    subtasks = parent.get("subtasks", [])
    next_sub_id = 1
    if subtasks:
        next_sub_id = max(s["id"] for s in subtasks) + 1

    gen_id = next_sub_id
    rev_id = next_sub_id + 1

    gen_deps = [depends_on_subtask] if depends_on_subtask else []
    output_path = f"/home/r.dovgan/cakb/rag/{module_name}"

    gen_subtask = {
        "id": gen_id,
        "title": f"Generate {module_name}/{wiki_filename}",
        "description": f"Generate wiki page {wiki_filename} for domain '{page_name}' in module {module_name}",
        "details": f"Files: {', '.join(file_list[:10])}",
        "status": "pending",
        "dependencies": gen_deps,
        # Custom metadata
        "type": "generate",
        "module": module_name,
        "source_path": f"/home/r.dovgan/mbp-rag/{module_name}",
        "output_path": output_path,
        "wiki_filename": wiki_filename,
        "file_list": file_list,
        "is_overview": is_overview,
    }

    rev_subtask = {
        "id": rev_id,
        "title": f"Review {module_name}/{wiki_filename}",
        "description": f"Review generated wiki page {wiki_filename}",
        "details": "",
        "status": "pending",
        "dependencies": [gen_id],
        # Custom metadata
        "type": "review",
        "module": module_name,
        "source_path": f"/home/r.dovgan/mbp-rag/{module_name}",
        "output_path": output_path,
        "wiki_filename": wiki_filename,
        "file_list": file_list,
        "is_overview": is_overview,
    }

    parent.setdefault("subtasks", []).extend([gen_subtask, rev_subtask])
    _set_tag_tasks(tasks)
    log.info(f"Created generate+review subtasks {parent_id}.{gen_id}/{parent_id}.{rev_id} for {wiki_filename}")
    return gen_id, rev_id


def find_subtask_by_type(parent_id: int, subtask_type: str) -> Optional[dict]:
    """Find a subtask by type within a parent task."""
    tasks = _get_tag_tasks()
    for t in tasks:
        if t["id"] == parent_id:
            for s in t.get("subtasks", []):
                if s.get("type") == subtask_type:
                    return s
    return None


def find_subtask_by_id(parent_id: int, subtask_id: int) -> Optional[dict]:
    """Find a specific subtask."""
    tasks = _get_tag_tasks()
    for t in tasks:
        if t["id"] == parent_id:
            for s in t.get("subtasks", []):
                if s["id"] == subtask_id:
                    return s
    return None


def has_any_tasks() -> bool:
    """Check if any tasks exist in Taskmaster."""
    tasks = _get_tag_tasks()
    return len(tasks) > 0


def get_all_tasks() -> list:
    """Get all tasks with their subtasks."""
    return _get_tag_tasks()


def get_task_by_id(task_id: int) -> Optional[dict]:
    """Get a specific task by ID."""
    tasks = _get_tag_tasks()
    for t in tasks:
        if t["id"] == task_id:
            return t
    return None


def is_module_complete(module_name: str) -> bool:
    """Check if all subtasks of a module's parent task are done."""
    tasks = _get_tag_tasks()
    for t in tasks:
        if t.get("module") == module_name:
            subtasks = t.get("subtasks", [])
            if not subtasks:
                return False
            return all(s["status"] == "done" for s in subtasks)
    return False


def get_module_progress(module_name: str) -> dict:
    """Get progress stats for a module."""
    tasks = _get_tag_tasks()
    for t in tasks:
        if t.get("module") == module_name:
            subtasks = t.get("subtasks", [])
            done = [s for s in subtasks if s["status"] == "done"]
            failed = [s for s in subtasks if s["status"] in ("failed",)]
            pending = [s for s in subtasks if s["status"] == "pending"]
            in_progress = [s for s in subtasks if s["status"] == "in-progress"]
            return {
                "status": t.get("status", "pending"),
                "total": len(subtasks),
                "done": len(done),
                "failed": len(failed),
                "pending": len(pending),
                "in_progress": len(in_progress),
                "completed_pages": [
                    s.get("wiki_filename", "") for s in done
                    if s.get("type") == "review"
                ],
                "failed_pages": [
                    s.get("wiki_filename", "") for s in failed
                    if s.get("type") in ("generate", "review")
                ],
            }
    return {
        "status": "pending", "total": 0, "done": 0,
        "failed": 0, "pending": 0, "in_progress": 0,
        "completed_pages": [], "failed_pages": [],
    }


def set_parent_status_if_complete(parent_id: int) -> bool:
    """
    Check if all subtasks are done and update parent status accordingly.
    Returns True if parent was marked done.
    """
    tasks = _get_tag_tasks()
    for t in tasks:
        if t["id"] == parent_id:
            subtasks = t.get("subtasks", [])
            if not subtasks:
                return False
            all_done = all(s["status"] == "done" for s in subtasks)
            any_failed = any(s["status"] == "failed" for s in subtasks)
            if all_done:
                t["status"] = "done"
                from datetime import datetime
                t["completed_at"] = datetime.now().isoformat()
                _set_tag_tasks(tasks)
                log.info(f"Parent task {parent_id} marked as done")
                return True
            elif any_failed and all(
                s["status"] in ("done", "failed") for s in subtasks
            ):
                t["status"] = "done"  # still mark as done, some pages just failed
                from datetime import datetime
                t["completed_at"] = datetime.now().isoformat()
                _set_tag_tasks(tasks)
                log.info(f"Parent task {parent_id} marked as done (with some failures)")
                return True
    return False
