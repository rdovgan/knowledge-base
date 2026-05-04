#!/bin/bash
clear
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MBP RAG Pipeline Status — $(date '+%H:%M:%S')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Процес
PID=$(pgrep -f "run_pipeline.py" | head -1)
if [ -n "$PID" ]; then
    echo "  🟢 Pipeline RUNNING (PID: $PID)"
    CPU=$(ps -p $PID -o %cpu --no-headers | tr -d ' ')
    MEM=$(ps -p $PID -o %mem --no-headers | tr -d ' ')
    echo "     CPU: ${CPU}%  MEM: ${MEM}%"
else
    echo "  🔴 Pipeline NOT running"
fi

# tmux
if tmux has-session -t cakb-pipeline 2>/dev/null; then
    echo "  📺 tmux: cakb-pipeline active"
fi

echo ""
echo "  Modules:"
echo "  ─────────────────────────────────────────────"

MODULES="mbp-utils redis parent-dal dataaccesslayer core-module channel-integration channel-batch-jobs web-messages mbp"

for mod in $MODULES; do
    STATE_FILE=~/cakb/rag/$mod/.state.json
    if [ -f "$STATE_FILE" ]; then
        STATUS=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('status','?'))" 2>/dev/null)
        PAGES=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(len(d.get('completed_pages',[])))" 2>/dev/null)
        FAILED=$(python3 -c "import json; d=json.load(open('$STATE_FILE')); print(len(d.get('failed_pages',[])))" 2>/dev/null)
        case $STATUS in
            completed)   ICON="✅" ;;
            in_progress) ICON="🔄" ;;
            failed)      ICON="❌" ;;
            *)           ICON="⏳" ;;
        esac
        echo "  $ICON  $mod — $STATUS (pages: $PAGES, failed: $FAILED)"
    else
        echo "  ⏳  $mod — pending"
    fi
done

echo ""
echo "  ─────────────────────────────────────────────"
TOTAL=$(find ~/cakb/rag -name "*.md" 2>/dev/null | grep -v "index\|README" | wc -l)
echo "  📄 Total wiki pages: $TOTAL"

echo ""
echo "  Last log entries:"
echo "  ─────────────────────────────────────────────"
tail -5 ~/cakb/logs/pipeline.log | grep -E "INFO|ERROR|WARNING" | sed 's/^/  /'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
