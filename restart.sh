#!/bin/bash

# --- fin API Server Restart Script ---

cd "$(dirname "$0")" || exit 1

LABEL="fin"
[ "$1" = "--dev" ] && LABEL="fin-dev"

echo "Restarting $LABEL server..."

echo "Stopping existing $LABEL server..."
bash ./stop.sh "$@"
if [ $? -ne 0 ]; then
    echo "Warning: stop.sh reported an issue, attempting to start anyway..."
fi

sleep 1
echo "Starting $LABEL server..."
bash ./run.sh "$@"
