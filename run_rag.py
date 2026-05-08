#!/usr/bin/env python3
"""
RAG Pipeline — Full runner.

Cron-safe: loads .env, PID lock, retry on index, resume on all steps.

Usage:
  python3 run_rag.py parse                    # Step 1 only
  python3 run_rag.py parse --module redis     # One module
  python3 run_rag.py group                    # Step 2
  python3 run_rag.py markdown                 # Step 3
  python3 run_rag.py enrich                   # Step 4
  python3 run_rag.py enrich --limit 10        # First 10 domains only
  python3 run_rag.py flows                    # Step 4.5: cross-domain flow docs
  python3 run_rag.py flows --limit 3          # Generate first 3 flows only
  python3 run_rag.py index                    # Step 5 (resume-safe)
  python3 run_rag.py all                      # Steps 1-6
  python3 run_rag.py query "how does booking work?"  # Query RAG
  python3 run_rag.py status                   # Show current state

Cron example:
  0 3 * * * cd /home/r.dovgan/cakb && python3 run_rag.py all >> logs/cron.log 2>&1
"""

import os
import sys
import json
import time
import logging
import argparse
import fcntl
from datetime import datetime
from pathlib import Path

# ── Bootstrap: project root ──────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Load .env BEFORE anything else ───────────────────────────────

def load_env():
    """Load .env file into os.environ (cron has no env)."""
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

load_env()

# ── Logging ──────────────────────────────────────────────────────

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "pipeline.log", encoding='utf-8'),
    ],
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

SOURCE_ROOT = PROJECT_ROOT / "sources"
# Support both layouts: sources/ or direct mbp-rag/
if not SOURCE_ROOT.exists():
    SOURCE_ROOT = Path("/home/r.dovgan/mbp-rag")

WIKI_DIR = PROJECT_ROOT / "rag"            # wiki markdown (inside submodule, git-managed)
DATA_DIR = PROJECT_ROOT / "data"          # pipeline data (outside submodule, safe from git ops)
PARSED_FILE = DATA_DIR / "parsed" / "parsed.json"
DOMAINS_FILE = DATA_DIR / "domains" / "domains.json"
VECTORSTORE_DIR = DATA_DIR / "vectorstore"
LOCK_FILE = PROJECT_ROOT / ".rag_pipeline.lock"

MODULES = {}
for mod_dir in sorted(SOURCE_ROOT.iterdir()):
    if mod_dir.is_dir() and not mod_dir.name.startswith('.'):
        # Check it has Java source files
        has_java = any(mod_dir.rglob("*.java"))
        if has_java:
            MODULES[mod_dir.name] = str(mod_dir)

# LLM config
LLM_API_KEY = os.environ.get("ZAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
LLM_MODEL = os.environ.get("LLM_MODEL", "glm-5-turbo")
LLM_FALLBACK = os.environ.get("LLM_FALLBACK_MODEL", "glm-4.7")

INDEX_MAX_RETRIES = int(os.environ.get("INDEX_MAX_RETRIES", "3"))

# ── PID Lock ─────────────────────────────────────────────────────

class PipelineLock:
    """Prevent concurrent pipeline runs."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._lock_file = None

    def __enter__(self):
        self._lock_file = open(self.lock_path, 'w')
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.write(f"{os.getpid()}\n{datetime.now().isoformat()}\n")
            self._lock_file.flush()
            return self
        except (IOError, OSError):
            # Read existing lock info
            pid = "?"
            try:
                with open(self.lock_path) as f:
                    pid = f.readline().strip()
            except:
                pass
            log.error(f"Pipeline already running (PID {pid}). Exiting.")
            sys.exit(1)

    def __exit__(self, *args):
        if self._lock_file:
            fcntl.flock(self._lock_file, fcntl.LOCK_UN)
            self._lock_file.close()
        try:
            self.lock_path.unlink()
        except:
            pass


# ── Step 1: Parse ─────────────────────────────────────────────────

def step_parse(modules=None, force=False):
    from rag_pipeline.java_parser import parse_module

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "parsed").mkdir(exist_ok=True)

    # Skip if all modules already parsed (unless --force or specific modules requested)
    if not force and not modules and PARSED_FILE.exists():
        try:
            with open(PARSED_FILE) as f:
                old = json.load(f)
            parsed_modules = {m['module'] for m in old.get('modules', [])}
            missing = set(MODULES.keys()) - parsed_modules
            if not missing:
                total = sum(m['stats']['classes_parsed'] for m in old['modules'])
                log.info(f"⏭  Parse: already done ({len(parsed_modules)} modules, {total} classes). Use --force to re-parse.")
                return
            else:
                log.info(f"Parse: missing modules {missing}, will parse those")
        except Exception:
            pass  # Corrupted file, re-parse

    target_modules = modules or list(MODULES.keys())
    results = {"created_at": datetime.now().isoformat(), "modules": []}

    # Load existing
    existing = {}
    if PARSED_FILE.exists():
        try:
            with open(PARSED_FILE) as f:
                old = json.load(f)
            for m in old.get('modules', []):
                existing[m['module']] = m
            log.info(f"Loaded existing parsed data: {len(existing)} modules")
        except Exception as e:
            log.warning(f"Could not load existing parsed data: {e}")

    for mod_name in target_modules:
        source_path = MODULES.get(mod_name)
        if not source_path or not os.path.isdir(source_path):
            log.warning(f"Module not found: {mod_name}")
            continue

        log.info(f"═══ Parsing module: {mod_name} ═══")
        start = time.time()
        try:
            result = parse_module(source_path, mod_name)
        except Exception as e:
            log.error(f"Parse failed for {mod_name}: {e}")
            continue
        elapsed = time.time() - start

        stats = result['stats']
        log.info(f"  {mod_name}: {stats['classes_parsed']} classes, "
                 f"{stats['properties_files']} properties, "
                 f"{stats['mapper_files']} mappers ({elapsed:.1f}s)")
        results['modules'].append(result)

    # Keep modules not re-parsed
    for mod_name, mod_data in existing.items():
        if mod_name not in target_modules:
            results['modules'].append(mod_data)

    # Atomic write
    tmp = str(PARSED_FILE) + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    os.replace(tmp, str(PARSED_FILE))

    total = sum(m['stats']['classes_parsed'] for m in results['modules'])
    log.info(f"═══ Parse complete: {len(results['modules'])} modules, {total} classes ═══")


# ── Step 2: Group ─────────────────────────────────────────────────

def step_group(force=False):
    from rag_pipeline.domain_grouper import group_all_modules

    # Skip if domains already exist and parsed file unchanged
    if not force and DOMAINS_FILE.exists() and PARSED_FILE.exists():
        parsed_mtime = PARSED_FILE.stat().st_mtime
        domains_mtime = DOMAINS_FILE.stat().st_mtime
        if domains_mtime > parsed_mtime:
            with open(DOMAINS_FILE) as f:
                domains = json.load(f)
            log.info(f"⏭  Group: already done ({len(domains)} domains). Use --force to re-group.")
            return

    (DATA_DIR / "domains").mkdir(parents=True, exist_ok=True)

    with open(PARSED_FILE) as f:
        parsed = json.load(f)

    domains = group_all_modules(parsed)

    tmp = str(DOMAINS_FILE) + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(domains, f, ensure_ascii=False, indent=1)
    os.replace(tmp, str(DOMAINS_FILE))

    channels = [d for d in domains if d.get('channel')]
    other = [d for d in domains if not d.get('channel')]
    log.info(f"═══ Grouping complete: {len(domains)} domains "
             f"({len(channels)} channel, {len(other)} core) ═══")


# ── Step 3: Markdown ─────────────────────────────────────────────

def step_markdown(force=False):
    from rag_pipeline.markdown_writer import generate_all_markdown

    # Skip if wiki dir exists and is newer than domains file
    if not force and WIKI_DIR.is_dir() and DOMAINS_FILE.exists():
        domains_mtime = DOMAINS_FILE.stat().st_mtime
        # Check index.md as proxy for wiki freshness
        index_file = WIKI_DIR / "index.md"
        if index_file.exists():
            wiki_mtime = index_file.stat().st_mtime
            if wiki_mtime > domains_mtime:
                md_count = sum(1 for _ in WIKI_DIR.rglob("*.md"))
                log.info(f"⏭  Markdown: already done ({md_count} files). Use --force to re-generate.")
                return

    with open(PARSED_FILE) as f:
        parsed = json.load(f)
    with open(DOMAINS_FILE) as f:
        domains = json.load(f)

    stats = generate_all_markdown(parsed, domains, str(WIKI_DIR))
    log.info(f"═══ Markdown complete: {stats['class_pages']} class pages, "
             f"{stats['domain_pages']} domain pages ═══")


# ── Step 4: Enrich ───────────────────────────────────────────────

def step_flows(limit=0, delay=2.0):
    """Generate cross-domain flow documents."""
    from rag_pipeline.flow_generator import generate_flows

    if not LLM_API_KEY:
        log.error("ZAI_API_KEY not set. Check .env file.")
        sys.exit(1)

    with open(DOMAINS_FILE) as f:
        domains = json.load(f)

    stats = generate_flows(
        domains=domains,
        output_dir=str(WIKI_DIR),
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        fallback_model=LLM_FALLBACK,
        delay=delay,
        limit=limit,
    )
    log.info(f"═══ Flow generation complete: {stats} ═══")


def step_enrich(limit=0, delay=1.0):
    from rag_pipeline.enricher import enrich_all_domains

    if not LLM_API_KEY:
        log.error("ZAI_API_KEY not set. Check .env file.")
        sys.exit(1)

    with open(PARSED_FILE) as f:
        parsed = json.load(f)
    with open(DOMAINS_FILE) as f:
        domains = json.load(f)

    stats = enrich_all_domains(
        domains=domains,
        parsed_data=parsed,
        output_dir=str(WIKI_DIR),
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        fallback_model=LLM_FALLBACK,
        delay=delay,
        limit=limit,
    )
    log.info(f"═══ Enrichment complete: {stats} ═══")


# ── Step 5: Index (with retry + resume) ──────────────────────────

def step_index():
    from rag_pipeline.indexer import build_vectorstore

    if not WIKI_DIR.is_dir():
        log.error(f"Wiki dir not found: {WIKI_DIR}. Run markdown step first.")
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, INDEX_MAX_RETRIES + 1):
        try:
            stats = build_vectorstore(
                wiki_dir=str(WIKI_DIR),
                store_dir=str(VECTORSTORE_DIR),
                collection_name="wiki_java",
            )
            log.info(f"═══ Index complete: {stats} ═══")
            return
        except Exception as e:
            log.error(f"Index attempt {attempt}/{INDEX_MAX_RETRIES} failed: {e}")
            if attempt < INDEX_MAX_RETRIES:
                wait = 30 * attempt
                log.info(f"Retrying in {wait}s...")
                time.sleep(wait)
            else:
                log.error(f"Index failed after {INDEX_MAX_RETRIES} attempts")
                sys.exit(1)


# ── Query ─────────────────────────────────────────────────────────

def cmd_query(query: str, top_k: int = 5):
    from rag_pipeline.indexer import query_rag

    results = query_rag(
        query=query,
        store_dir=str(VECTORSTORE_DIR),
        top_k=top_k,
    )

    if not results:
        print("No results found.")
        return

    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"Results: {len(results)}")
    print(f"{'='*60}\n")

    for i, r in enumerate(results, 1):
        print(f"─── Result {i} (distance: {r['distance']:.3f}) ───")
        print(f"Source: {r['metadata'].get('source_file', '?')}")
        print()
        text = r['text']
        if len(text) > 800:
            text = text[:800] + "..."
        print(text)
        print()


# ── Status ───────────────────────────────────────────────────────

def cmd_status():
    print("═══ RAG Pipeline Status ═══\n")

    # Parsed
    if PARSED_FILE.exists():
        with open(PARSED_FILE) as f:
            d = json.load(f)
        for m in d.get('modules', []):
            s = m.get('stats', {})
            print(f"  {m['module']}: {s.get('classes_parsed', 0)} classes")
    else:
        print("  No parsed data yet.")

    # Domains
    if DOMAINS_FILE.exists():
        with open(DOMAINS_FILE) as f:
            domains = json.load(f)
        channels = sum(1 for d in domains if d.get('channel'))
        print(f"\n  Domains: {len(domains)} ({channels} channel, {len(domains)-channels} core)")

    # Wiki
    if WIKI_DIR.is_dir():
        md_count = sum(1 for _ in WIKI_DIR.rglob("*.md"))
        print(f"  Wiki pages: {md_count}")

    # Vectorstore
    if VECTORSTORE_DIR.is_dir():
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
            coll = client.get_collection("wiki_java")
            print(f"  Indexed chunks: {coll.count()}")
        except Exception:
            print("  Vectorstore: empty or corrupted")

    # Lock
    if LOCK_FILE.exists():
        with open(LOCK_FILE) as f:
            lines = f.read().strip().split('\n')
        print(f"\n  ⚠️  Lock file present (PID {lines[0] if lines else '?'})")

    # Env
    print(f"\n  ZAI_API_KEY: {'✅ set' if os.environ.get('ZAI_API_KEY') else '❌ missing'}")
    print(f"  .env file: {'✅ found' if (PROJECT_ROOT / '.env').exists() else '❌ missing'}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAG Pipeline Runner")
    parser.add_argument('command', choices=[
        'parse', 'group', 'markdown', 'enrich', 'flows', 'index', 'all', 'query', 'status'
    ])
    parser.add_argument('query_text', nargs='*', help='Query text (for query command)')
    parser.add_argument('--module', '-m', help='Module name(s), comma-separated')
    parser.add_argument('--limit', '-l', type=int, default=0, help='Max domains to enrich')
    parser.add_argument('--delay', '-d', type=float, default=1.0, help='Delay between LLM calls (sec)')
    parser.add_argument('--top-k', '-k', type=int, default=5, help='Query top K results')
    parser.add_argument('--force', '-f', action='store_true', help='Force re-run completed steps')

    args = parser.parse_args()

    # Status doesn't need lock
    if args.command == 'status':
        cmd_status()
        return

    # Query doesn't need lock
    if args.command == 'query':
        query_text = ' '.join(args.query_text) if args.query_text else ''
        if not query_text:
            print('Usage: python3 run_rag.py query "your question"')
            sys.exit(1)
        cmd_query(query_text, args.top_k)
        return

    # All other commands need lock
    with PipelineLock(LOCK_FILE):
        log.info(f"═══════════════════════════════════════════")
        log.info(f"  RAG Pipeline — {args.command}")
        log.info(f"  PID: {os.getpid()}, {datetime.now().isoformat()}")
        log.info(f"═══════════════════════════════════════════")

        if args.command == 'parse':
            modules = args.module.split(',') if args.module else None
            step_parse(modules, force=args.force)

        elif args.command == 'group':
            step_group(force=args.force)

        elif args.command == 'markdown':
            step_markdown(force=args.force)

        elif args.command == 'enrich':
            step_enrich(limit=args.limit, delay=args.delay)

        elif args.command == 'flows':
            step_flows(limit=args.limit, delay=args.delay)

        elif args.command == 'index':
            step_index()

        elif args.command == 'all':
            step_parse(force=args.force)
            step_group(force=args.force)
            step_markdown(force=args.force)
            step_enrich(limit=args.limit, delay=args.delay)
            step_flows(limit=args.limit, delay=args.delay)
            step_index()

        log.info(f"═══════════════════════════════════════════")
        log.info(f"  Done. {datetime.now().isoformat()}")
        log.info(f"═══════════════════════════════════════════")


if __name__ == '__main__':
    main()
