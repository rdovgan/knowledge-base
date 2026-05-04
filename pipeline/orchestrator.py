"""
Orchestrator — 2-phase pipeline with CrewAI agents.

Phase 1 (Explore):  Scan each module → decompose → identify pages → create tasks
Phase 2 (Generate): For each module, for each page → generate wiki → review

Runs continuously until all modules are done.
State persisted in pipeline_state.json (no external task-master CLI).

Large module handling:
  - Small (<200 files): explore directly
  - Large (200-2000): split into domains, explore each
  - Huge (>2000 like mbp): split into sub-domains, each gets pages
"""

import json
import os
import sys
import logging
import time
from datetime import datetime
from pathlib import Path
import yaml

from .crews.explorer_crew import run_explorer
from .crews.wiki_crew import run_wiki_generation
from .decomposer import decompose_module
from . import pipeline_state as ps

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler('/home/r.dovgan/cakb/logs/pipeline.log'),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


def load_modules_config() -> list:
    config_path = '/home/r.dovgan/cakb/config/modules.yaml'
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    # Deduplicate by name (keep first occurrence)
    seen = set()
    modules = []
    for m in cfg['modules']:
        if m.get('enabled', True) and m['name'] not in seen:
            modules.append(m)
            seen.add(m['name'])
    return modules


# ── Phase 1: Exploration ───────────────────────────────────────────

def explore_all_modules():
    """
    Explore the next module that needs exploration.
    Returns True if something was explored, False if nothing to do.
    """
    module = ps.get_next_module_to_explore()
    if not module:
        return False

    module_name = module["name"]
    source_path = module["source_path"]
    output_path = module["output_path"]

    log.info(f"═══ EXPLORING: {module_name} ═══")
    ps.set_module_status(module_name, "exploring")
    os.makedirs(output_path, exist_ok=True)

    # Decompose to understand scale
    decomposition = decompose_module(module_name, source_path)
    strategy = decomposition["strategy"]
    domains = decomposition["domains"]

    log.info(f"  Strategy: {strategy}, {len(domains)} domain(s)")

    try:
        # Run explorer (handles large modules internally)
        plan = run_explorer(source_path, module_name)
    except Exception as e:
        log.error(f"Explorer crashed for {module_name}: {e}")
        ps.set_module_status(module_name, "failed")
        return True

    if isinstance(plan, dict) and 'error' in plan:
        log.error(f"Explorer failed for {module_name}: {plan['error']}")
        ps.set_module_status(module_name, "failed")
        return True

    # Build page list from plan
    pages = []

    # Additional pages (overview, configuration)
    for page in plan.get('additional_pages', []):
        pages.append(_make_page_entry(page, is_overview=True))

    # Domain pages
    for domain in plan.get('domains', []):
        pages.append(_make_page_entry(domain, is_overview=False))

    ps.set_pages_for_module(module_name, pages)

    log.info(f"  {module_name}: {len(pages)} pages to generate")
    for p in pages:
        file_count = len(p.get("files", []))
        log.info(f"    • {p['wiki_filename']} ({file_count} files)")

    return True


def _make_page_entry(page: dict, is_overview: bool = False) -> dict:
    """Create a page entry for pipeline state."""
    return {
        "name": page.get('name', 'unknown'),
        "wiki_filename": page.get('wiki_filename', 'unknown.md'),
        "status": "pending",
        "type": "generate",
        "files": page.get('files', [])[:200],  # cap at 200
        "is_overview": is_overview,
        "attempts": 0,
        "score": None,
        "error": None,
        "started_at": None,
        "completed_at": None,
    }


# ── Phase 2: Generate + Review ─────────────────────────────────────

def generate_next_page():
    """
    Generate the next pending wiki page.
    Returns True if a page was processed, False if nothing to do.
    """
    next_item = ps.get_next_page_to_generate()
    if not next_item:
        return False

    module_name = next_item["module_name"]
    output_path = next_item["output_path"]
    page = next_item["page"]
    page_name = page["name"]
    wiki_filename = page["wiki_filename"]
    file_list = page.get("files", [])

    log.info(f"═══ GENERATING: {module_name}/{wiki_filename} ═══ "
             f"({len(file_list)} files)")

    # Update module status
    module = ps.get_module(module_name)
    if module and module["status"] in ("pending", "exploring"):
        ps.set_module_status(module_name, "generating")

    ps.set_page_status(module_name, page_name, "generating")
    os.makedirs(output_path, exist_ok=True)

    try:
        review = run_wiki_generation(
            module_name=module_name,
            domain_name=page_name,
            file_list=file_list,
            output_path=output_path,
            wiki_filename=wiki_filename,
            max_attempts=3,
        )
    except Exception as e:
        log.error(f"Generator crashed for {module_name}/{wiki_filename}: {e}")
        ps.set_page_status(module_name, page_name, "failed", error=str(e))
        ps.check_module_complete(module_name)
        return True

    decision = review.get('decision', 'unknown')
    score = review.get('score', 0)

    if decision == 'approved':
        ps.set_page_status(module_name, page_name, "done", score=score)
        log.info(f"✅ {module_name}/{wiki_filename} approved (score: {score})")
    elif decision == 'needs-human-review':
        ps.set_page_status(module_name, page_name, "done", score=score)
        log.warning(f"⚠️  {module_name}/{wiki_filename} needs human review")
    else:
        ps.set_page_status(module_name, page_name, "failed",
                          error=f"Rejected after {review.get('attempts', 3)} attempts")
        log.error(f"❌ {module_name}/{wiki_filename} failed")

    ps.check_module_complete(module_name)
    return True


# ── Progress tracking ──────────────────────────────────────────────

def print_progress():
    """Print current progress summary."""
    summary = ps.get_summary()
    stats = ps.get_stats()

    log.info(f"─" * 50)
    log.info(f"Progress: {stats['done_pages']}/{stats['total_pages']} pages "
             f"({stats['progress_pct']}%), "
             f"{stats['done_modules']}/{stats['total_modules']} modules")

    for m in summary["modules"]:
        status_icons = {
            "pending": "⏳", "exploring": "🔍", "generating": "⚙️",
            "done": "✅", "failed": "❌"
        }
        icon = status_icons.get(m["status"], "?")
        current = f" → {m['current_page']}" if m.get("current_page") else ""
        log.info(f"  {icon} {m['name']}: "
                 f"{m['done']}/{m['total_pages']} pages{current}")
    log.info(f"─" * 50)


def update_readme():
    """Update the global RAG README with current status."""
    summary = ps.get_summary()

    lines = [
        '# RAG Pipeline Status\n',
        f'Updated: {datetime.now().isoformat()}\n\n',
        '| Module | Status | Done | Failed | Total |\n',
        '|--------|--------|------|--------|-------|\n',
    ]

    for m in summary["modules"]:
        icon = {"pending": "⏳", "exploring": "🔍", "generating": "⚙️",
                "done": "✅", "failed": "❌"}.get(m["status"], "?")
        lines.append(
            f"| {m['name']} | {icon} {m['status']} | "
            f"{m['done']} | {m['failed']} | {m['total_pages']} |\n"
        )

    os.makedirs('/home/r.dovgan/cakb/rag', exist_ok=True)
    with open('/home/r.dovgan/cakb/rag/README.md', 'w') as f:
        f.writelines(lines)


def generate_module_index(module_name: str, output_path: str):
    """Generate index.md for a completed module."""
    module = ps.get_module(module_name)
    if not module:
        return

    done_pages = [p for p in module.get("pages", []) if p["status"] == "done"]
    failed_pages = [p for p in module.get("pages", []) if p["status"] == "failed"]

    lines = [f'# {module_name} — Wiki Index\n\n']
    lines.append(f'Generated: {datetime.now().isoformat()}\n\n')

    if done_pages:
        lines.append('## ✅ Approved Pages\n\n')
        for p in done_pages:
            lines.append(f'- [{p["name"]}](./{p["wiki_filename"]})\n')
        lines.append('\n')

    if failed_pages:
        lines.append('## ⚠️ Needs Human Review\n\n')
        for p in failed_pages:
            lines.append(f'- [{p["name"]}](./{p["wiki_filename"]})\n')

    os.makedirs(output_path, exist_ok=True)
    with open(f'{output_path}/index.md', 'w') as f:
        f.writelines(lines)


# ── Main pipeline ──────────────────────────────────────────────────

def run_pipeline(reset: bool = False):
    """
    Main pipeline — runs continuously until all modules are done.
    """
    log.info("=" * 60)
    log.info("🚀 Pipeline started")
    os.makedirs('/home/r.dovgan/cakb/logs', exist_ok=True)
    os.makedirs('/home/r.dovgan/cakb/rag', exist_ok=True)

    if reset:
        ps.reset_state()
        log.info("State reset")

    # Initialize modules from config
    modules = load_modules_config()
    ps.init_modules(modules)

    total_processed = 0

    while not ps.is_pipeline_complete():
        did_something = False

        # Phase 1: Explore (one module per iteration)
        if explore_all_modules():
            did_something = True
            total_processed += 1
            print_progress()

        # Phase 2: Generate (one page per iteration)
        if generate_next_page():
            did_something = True
            total_processed += 1
            print_progress()

        if not did_something:
            log.warning("Nothing to process but pipeline not complete")
            summary = ps.get_summary()
            for m in summary["modules"]:
                if m["status"] not in ("done", "failed"):
                    log.warning(f"  Stuck: {m['name']} "
                               f"(status={m['status']}, pages={m['total_pages']})")
            break

    # Generate indexes for completed modules
    state = ps.get_full_state()
    for m in state.get("modules", []):
        if m["status"] == "done" and m.get("pages"):
            generate_module_index(m["name"], m["output_path"])

    update_readme()
    stats = ps.get_stats()
    log.info("=" * 60)
    log.info(f"🏁 Pipeline complete!")
    log.info(f"   Modules: {stats['done_modules']}/{stats['total_modules']}")
    log.info(f"   Pages:   {stats['done_pages']}/{stats['total_pages']} "
             f"({stats['failed_pages']} failed)")
    log.info("=" * 60)


if __name__ == '__main__':
    reset_flag = "--reset" in sys.argv
    run_pipeline(reset=reset_flag)
