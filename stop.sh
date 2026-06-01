#!/bin/bash

# --- fin API Server Stop Script ---

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

DEV=0
[ "$1" = "--dev" ] && DEV=1

if [ "$DEV" = "1" ]; then
    PID_FILE="$SCRIPT_DIR/fin-dev.pid"
    PORT=18888
    LABEL="fin-dev"
else
    PID_FILE="$SCRIPT_DIR/fin.pid"
    PORT=8888
    LABEL="fin"
fi

cd "$SCRIPT_DIR" || exit 1

PID=""
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "Process $PID is not running. Cleaning up stale PID file."
        rm -f "$PID_FILE"
        PID=""
    fi
fi

# Fallback: search by script name (filtered by mode) or port listener
if [ -z "$PID" ]; then
    echo "PID file not found or stale. Searching for $LABEL server process..."
    for CAND in $(pgrep -u "$(id -u -n)" -f "serve\.py" 2>/dev/null); do
        ARGS=$(ps -p "$CAND" -o args= 2>/dev/null)
        if echo "$ARGS" | grep -q -- "--dev"; then
            IS_DEV=1
        else
            IS_DEV=0
        fi
        if [ "$IS_DEV" = "$DEV" ]; then
            PID="$CAND"
            break
        fi
    done
    if [ -z "$PID" ]; then
        PID=$(lsof -t -i:$PORT -sTCP:LISTEN 2>/dev/null | head -n 1)
    fi
fi

if [ -z "$PID" ]; then
    echo "$LABEL server is not running."
    exit 0
fi

CHILDREN=$(pgrep -P "$PID" 2>/dev/null)
PIDS_TO_KILL="$PID $CHILDREN"

echo "Stopping $LABEL server (PID: $PID, children: ${CHILDREN:-none})..."

kill -TERM $PIDS_TO_KILL 2>/dev/null

for i in {1..10}; do
    ALIVE=0
    for P in $PIDS_TO_KILL; do
        if kill -0 "$P" 2>/dev/null; then
            ALIVE=1
            break
        fi
    done
    [ "$ALIVE" -eq 0 ] && break
    sleep 0.5
done

REMAINING=""
for P in $PIDS_TO_KILL; do
    kill -0 "$P" 2>/dev/null && REMAINING="$REMAINING $P"
done

if [ -n "$REMAINING" ]; then
    echo "Some processes ($REMAINING) did not stop gracefully. Sending SIGKILL..."
    kill -KILL $REMAINING 2>/dev/null
    sleep 0.5
fi

STILL_ALIVE=""
for P in $PIDS_TO_KILL; do
    kill -0 "$P" 2>/dev/null && STILL_ALIVE="$STILL_ALIVE $P"
done

if [ -z "$STILL_ALIVE" ]; then
    echo "$LABEL server stopped."
    rm -f "$PID_FILE"
else
    echo "ERROR: Failed to stop processes: $STILL_ALIVE"
    exit 1
fi
