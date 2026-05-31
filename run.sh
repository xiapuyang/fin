#!/bin/bash

# --- fin API Server Start Script ---

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

DEV=0
[ "$1" = "--dev" ] && DEV=1

if [ "$DEV" = "1" ]; then
    PID_FILE="$SCRIPT_DIR/fin-dev.pid"
    PORT=18899
    LOG_FILE="logs/fin-dev.log"
    SERVE_ARGS="--dev"
    LABEL="fin-dev"
else
    PID_FILE="$SCRIPT_DIR/fin.pid"
    PORT=8899
    LOG_FILE="logs/fin.log"
    SERVE_ARGS=""
    LABEL="fin"
fi

cd "$SCRIPT_DIR" || exit 1

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "$LABEL server is already running (PID: $PID). Stop it first."
        exit 1
    else
        echo "Found stale PID file (PID: $PID is dead). Cleaning up..."
        rm "$PID_FILE"
    fi
fi

# Check if the port is already occupied before attempting to start
OCCUPANT=$(lsof -t -i:$PORT -sTCP:LISTEN 2>/dev/null | head -n 1)
if [ -n "$OCCUPANT" ]; then
    echo "ERROR: Port $PORT is already in use by PID $OCCUPANT. Run ./stop.sh${SERVE_ARGS:+ --dev} first."
    exit 1
fi

mkdir -p logs
uv run python serve.py $SERVE_ARGS \
    >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

# Wait up to 15s for the port to bind
echo "Waiting for $LABEL server to bind port $PORT..."
SUCCESS=0
i=1
while [ $i -le 30 ]; do
    MY_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -z "$MY_PID" ]; then
        sleep 0.5
        i=$((i + 1))
        continue
    fi

    LISTENER_PIDS=$(lsof -t -i:$PORT 2>/dev/null)
    for LPID in $LISTENER_PIDS; do
        if [ "$LPID" = "$MY_PID" ]; then
            SUCCESS=1
            break 2
        fi
        L_PPID=$(ps -o ppid= -p "$LPID" 2>/dev/null | tr -d ' ')
        if [ -n "$L_PPID" ] && [ "$L_PPID" = "$MY_PID" ]; then
            SUCCESS=1
            break 2
        fi
    done

    if [ $((i % 6)) -eq 0 ]; then
        echo "Still waiting... (${i}s elapsed)"
    fi

    sleep 0.5
    i=$((i + 1))
done

if [ "$SUCCESS" = "1" ]; then
    echo "$LABEL server started (PID: $(cat "$PID_FILE")). Listening on http://localhost:$PORT"
    exit 0
else
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "ERROR: Port $PORT is occupied by another process."
    else
        echo "ERROR: $LABEL server failed to bind port $PORT within 15s. Check $LOG_FILE."
    fi
    exit 1
fi
