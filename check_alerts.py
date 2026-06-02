#!/usr/bin/env python3
"""Cron entry point: check stock alerts and send email notifications."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fin.logger import setup_logging
from fin.services.alert_checker import check_condition, run_check  # noqa: F401

setup_logging("check-alerts")


def main() -> None:
    """Parse CLI args and run one alert check cycle."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true", help="Skip market-state check (for testing)"
    )
    args = parser.parse_args()
    run_check(force=args.force)


if __name__ == "__main__":
    main()
