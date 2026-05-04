#!/bin/bash

# --- fin API Server Stop Script ---

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/fin.pid"

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

# Fallback: search by script name or port listener
if [ -z "$PID" ]; then
    echo "PID file not found or stale. Searching for fin server process..."
    # Try matching the serve.py script, then the uvicorn module path
    PID=$(pgrep -u "$(id -u -n)" -f "serve\.py" | head -n 1)
    if [ -z "$PID" ]; then
        PID=$(lsof -t -i:8899 -sTCP:LISTEN 2>/dev/null | head -n 1)
    fi
fi

if [ -z "$PID" ]; then
    echo "fin server is not running."
    exit 0
fi

CHILDREN=$(pgrep -P "$PID" 2>/dev/null)
PIDS_TO_KILL="$PID $CHILDREN"

echo "Stopping fin server (PID: $PID, children: ${CHILDREN:-none})..."

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
    echo "fin server stopped."
    rm -f "$PID_FILE"
else
    echo "ERROR: Failed to stop processes: $STILL_ALIVE"
    exit 1
fi
