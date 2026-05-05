#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MBP RAG Pipeline — wrapper script
#
# Usage:
#   ./run_pipeline.sh              # Run all steps (skips completed)
#   ./run_pipeline.sh --force      # Force re-run everything
#   ./run_pipeline.sh --status     # Show status
#   ./run_pipeline.sh --stop       # Kill running pipeline
#   ./run_pipeline.sh --index      # Run only index step (resume)
#   ./run_pipeline.sh --enrich     # Run only enrich step
#   ./run_pipeline.sh --reset      # Delete all data and re-run
#
# Cron:
#   0 * * * * /home/r.dovgan/cakb/scripts/run_pipeline.sh
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

PROJECT="/home/r.dovgan/cakb"
cd "$PROJECT"

# ── Status ──────────────────────────────────────────────────
if [ "${1:-}" = "--status" ]; then
    python3 run_rag.py status
    exit 0
fi

# ── Stop ────────────────────────────────────────────────────
if [ "${1:-}" = "--stop" ]; then
    pkill -f "run_rag.py" 2>/dev/null || true
    rm -f .rag_pipeline.lock
    echo "✅ Stopped"
    exit 0
fi

# ── Reset ───────────────────────────────────────────────────
if [ "${1:-}" = "--reset" ]; then
    pkill -f "run_rag.py" 2>/dev/null || true
    rm -f .rag_pipeline.lock
    rm -rf rag_v2/parsed rag_v2/domains rag_v2/vectorstore
    rm -rf rag
    echo "✅ All data deleted. Running from scratch..."
    exec python3 run_rag.py all
fi

# ── Single step ─────────────────────────────────────────────
if [ "${1:-}" = "--index" ]; then
    exec python3 run_rag.py index
fi

if [ "${1:-}" = "--enrich" ]; then
    exec python3 run_rag.py enrich
fi

# ── Full pipeline (default) ─────────────────────────────────
if [ "${1:-}" = "--force" ]; then
    exec python3 run_rag.py all --force
fi

exec python3 run_rag.py all
