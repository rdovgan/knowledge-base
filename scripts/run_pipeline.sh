#!/bin/bash
LOCK=/tmp/cakb_pipeline.lock
LOG=/home/r.dovgan/cakb/logs/pipeline.log
PROJECT=/home/r.dovgan/cakb
SESSION="cakb-pipeline"

if [ -f "$LOCK" ]; then
    echo "[$(date)] Already running (lock exists), skipping" >> "$LOG"
    exit 0
fi

touch "$LOCK"
trap "rm -f $LOCK" EXIT INT TERM

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[$(date)] tmux session $SESSION already active" >> "$LOG"
    exit 0
fi

echo "[$(date)] Starting pipeline in tmux session: $SESSION" >> "$LOG"

tmux new-session -d -s "$SESSION" \
    "cd $PROJECT && python3 run_pipeline.py >> $LOG 2>&1"

echo "[$(date)] Pipeline launched in background" >> "$LOG"
