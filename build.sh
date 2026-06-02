#!/usr/bin/env bash
set -euo pipefail
exec uv run python scripts/build.py "$@"
