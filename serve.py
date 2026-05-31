#!/usr/bin/env python3
"""Run the fin API server.

Usage:
    uv run python serve.py          # prod: data/, port 8899
    uv run python serve.py --dev    # dev:  data-dev/, port 18899, hot reload

Both modes can run concurrently — different ports, different SQLite files.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dev",
        action="store_true",
        help="use data-dev/, port 18899, hot reload",
    )
    args = parser.parse_args()

    if args.dev:
        os.environ["FIN_DEV"] = "1"

    # Import after env is set so fin.config picks up FIN_DEV.
    import uvicorn

    from fin.config import API_HOST, API_PORT

    uvicorn.run("fin.api:app", host=API_HOST, port=API_PORT, reload=args.dev)


if __name__ == "__main__":
    main()
