#!/usr/bin/env bash
# Build Fin desktop installers.
#
# Examples:
#   ./build.sh                        # Mac, native arch (default)
#   ./build.sh --target all           # all targets for this platform
#   ./build.sh --target mac-arm64
#   ./build.sh --target mac-intel
#   ./build.sh --target windows       # requires Windows + Inno Setup
#   ./build.sh --version v1.2.0       # override version string
set -euo pipefail
exec uv run python scripts/build.py "$@"
