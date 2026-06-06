"""One-time data directory migration.

When the configured DATA_DIR changes (e.g. Windows path upgraded from ~/.fin/data
to %LOCALAPPDATA%\\Fin\\Fin), this module detects stale legacy data and copies it
to the new location so users don't lose their database on first launch.

Migration criteria (all must be true):
  1. FIN_DATA_DIR is not explicitly set (user-specified paths are never auto-filled).
  2. Current DATA_DIR has no fin.db.
  3. A legacy directory exists that contains fin.db.
  4. The legacy directory is different from DATA_DIR.

Only flat files are copied (no subdirectories). The legacy directory is left
intact as a backup — the user can delete it manually.
"""

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


# Ordered list of legacy locations to probe, most-recent first.
# Paths are evaluated at call time so they reflect the actual home directory.
def _legacy_candidates(home_fin: Path, project_root: Path) -> list[Path]:
    return [
        home_fin / "data",  # Windows script mode before platformdirs (v0.2.x)
        project_root / "data",  # All platforms before ~/.fin migration
    ]


def migrate_data_dir(data_dir: Path, home_fin: Path, project_root: Path) -> bool:
    """Copy legacy data files to data_dir if data_dir has no fin.db.

    Skipped when FIN_DATA_DIR is explicitly set — the user chose that path
    intentionally, so auto-filling it would prevent starting with an empty dir.

    Returns True if a migration was performed, False otherwise.
    """
    if os.environ.get("FIN_DATA_DIR"):
        return False

    if (data_dir / "fin.db").exists():
        return False

    for legacy_dir in _legacy_candidates(home_fin, project_root):
        if legacy_dir.resolve() == data_dir.resolve():
            continue
        if not (legacy_dir / "fin.db").exists():
            continue

        logger.warning(
            "Legacy data detected at %s — current DATA_DIR is %s. "
            "Copying data files to new location.",
            legacy_dir,
            data_dir,
        )
        _copy_files(legacy_dir, data_dir)
        logger.info(
            "Migration complete. Legacy directory %s was left intact as backup.",
            legacy_dir,
        )
        return True

    return False


def _copy_files(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.is_file():
            shutil.copy2(item, dst / item.name)
            logger.info("  %s → %s", item.name, dst / item.name)
