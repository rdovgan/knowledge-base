#!/bin/bash
clear
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MBP RAG Pipeline Status — $(date '+%H:%M:%S')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Process
PID=$(pgrep -f "run_pipeline.py" | head -1)
if [ -n "$PID" ]; then
    echo "  🟢 Pipeline RUNNING (PID: $PID)"
    CPU=$(ps -p $PID -o %cpu --no-headers | tr -d ' ')
    MEM=$(ps -p $PID -o %mem --no-headers | tr -d ' ')
    echo "     CPU: ${CPU}%  MEM: ${MEM}%"
else
    echo "  🔴 Pipeline NOT running (single-task mode — normal between runs)"
fi

# Lock file
if [ -f /tmp/cakb_pipeline.lock ]; then
    echo "  🔒 Lock file present"
fi

echo ""
echo "  Taskmaster Tasks:"
echo "  ─────────────────────────────────────────────"
task-master list --tag pipeline 2>/dev/null | grep -v "^✓" | grep -v "Anonymous" | head -30

echo ""
echo "  Next Task:"
echo "  ─────────────────────────────────────────────"
task-master next --tag pipeline 2>/dev/null | grep -v "^✓" | grep -v "Anonymous" | head -10

echo ""
echo "  ─────────────────────────────────────────────"
TOTAL=$(find ~/cakb/rag -name "*.md" 2>/dev/null | grep -v "index\|README" | wc -l)
echo "  📄 Total wiki pages: $TOTAL"

echo ""
echo "  Last log entries:"
echo "  ─────────────────────────────────────────────"
tail -8 ~/cakb/logs/pipeline.log | grep -E "INFO|ERROR|WARNING|===" | sed 's/^/  /'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
