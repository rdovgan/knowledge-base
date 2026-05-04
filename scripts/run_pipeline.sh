#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MBP RAG Pipeline Runner with tmux
#
# Usage:
#   ./run_pipeline.sh            # Start pipeline in tmux session
#   ./run_pipeline.sh --reset    # Reset state and start fresh
#   ./run_pipeline.sh --status   # Show current status
#   ./run_pipeline.sh --attach   # Attach to running pipeline
#   ./run_pipeline.sh --stop     # Stop running pipeline
#   ./run_pipeline.sh --restart  # Stop + start fresh
#
# The pipeline runs inside a tmux session named "cakb".
# Detach: Ctrl+B then D
# Re-attach: ./run_pipeline.sh --attach
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SESSION="cakb"
PROJECT="/home/r.dovgan/cakb"
LOG="/home/r.dovgan/cakb/logs/pipeline.log"

mkdir -p /home/r.dovgan/cakb/logs

# ── Status ──────────────────────────────────────────────────
if [ "$1" = "--status" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  MBP RAG Pipeline Status"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # tmux session
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        PID=$(tmux list-panes -t "$SESSION" -F "#{pane_pid}" 2>/dev/null | head -1)
        echo "  🟢 RUNNING in tmux session '$SESSION'"
        if [ -n "$PID" ]; then
            UPTIME=$(ps -p $PID -o etime --no-headers 2>/dev/null | tr -d ' ')
            echo "     PID: $PID  Uptime: $UPTIME"
        fi
    else
        echo "  🔴 NOT running (no tmux session '$SESSION')"
    fi

    # State
    if [ -f "$PROJECT/pipeline_state.json" ]; then
        echo ""
        echo "  Modules & Pages:"
        python3 -c "
import json, sys
state = json.load(open('$PROJECT/pipeline_state.json'))
icons = {'pending':'⏳','exploring':'🔍','generating':'⚙️','done':'✅','failed':'❌'}
for m in state.get('modules', []):
    pages = m.get('pages', [])
    done = sum(1 for p in pages if p['status'] == 'done')
    fail = sum(1 for p in pages if p['status'] == 'failed')
    pend = sum(1 for p in pages if p['status'] == 'pending')
    gen  = sum(1 for p in pages if p['status'] == 'generating')
    icon = icons.get(m['status'], '?')
    print(f'  {icon} {m[\"name\"]:25s} {done}/{len(pages)} pages ({fail} failed, {pend} pending)')
    for p in pages:
        pi = icons.get(p['status'], '?')
        score = f' ({p[\"score\"]})' if p.get('score') else ''
        print(f'    {pi} {p[\"wiki_filename\"]}{score}')
"
    else
        echo "  No state file (pipeline not initialized yet)"
    fi

    echo ""
    echo "  Wiki pages on disk: $(find ~/cakb/rag -name '*.md' 2>/dev/null | grep -v 'index\|README' | wc -l)"
    echo ""
    echo "  Recent logs:"
    tail -8 "$LOG" 2>/dev/null | grep -v "LiteLLM" | sed 's/^/  /'
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
fi

# ── Attach ──────────────────────────────────────────────────
if [ "$1" = "--attach" ]; then
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        exec tmux attach -t "$SESSION"
    else
        echo "❌ No running session. Start with: $0"
        exit 1
    fi
fi

# ── Stop ────────────────────────────────────────────────────
if [ "$1" = "--stop" ]; then
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux kill-session -t "$SESSION"
        echo "✅ Stopped session '$SESSION'"
    else
        echo "Session '$SESSION' not running"
    fi
    exit 0
fi

# ── Restart = stop + reset + start ─────────────────────────
if [ "$1" = "--restart" ]; then
    $0 --stop 2>/dev/null
    rm -f "$PROJECT/pipeline_state.json"
    echo "✅ State reset, starting fresh..."
    set -- --reset
fi

# ── Start pipeline in tmux ─────────────────────────────────

# Kill existing session if any
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "⚠️  Session '$SESSION' already running."
    echo "   Attach:  $0 --attach"
    echo "   Stop:    $0 --stop"
    echo "   Restart: $0 --restart"
    exit 1
fi

# Build command
CMD="cd $PROJECT && python3 run_pipeline.py $@"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🚀 Starting pipeline in tmux session '$SESSION'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Commands:"
echo "    Attach:    $0 --attach"
echo "    Status:    $0 --status"
echo "    Stop:      $0 --stop"
echo "    Restart:   $0 --restart"
echo ""
echo "  tmux shortcuts:"
echo "    Detach:    Ctrl+B then D"
echo "    Scroll:    Ctrl+B then [ (q to exit)"
echo ""
echo "  Starting in 2s..."
sleep 2

# Create tmux session, run pipeline
tmux new-session -d -s "$SESSION" -c "$PROJECT" "$CMD"

# Also tee output to log file (via pipe-pane)
tmux pipe-pane -t "$SESSION" "cat >> $LOG"

echo "✅ Pipeline started in tmux session '$SESSION'"
