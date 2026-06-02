#!/usr/bin/env python3
"""Package Fin into a distributable installer.

Usage:
    uv run python scripts/build.py                  # Mac, native arch (default)
    uv run python scripts/build.py --target all     # all targets for this platform
    uv run python scripts/build.py --target mac-intel
    uv run python scripts/build.py --target windows  # must run on Windows

Targets:
    mac         Mac DMG, native arch (arm64 on Apple Silicon, x86_64 on Intel)
    mac-arm64   Mac DMG, Apple Silicon
    mac-intel   Mac DMG, Intel x86_64
    windows     Windows installer via Inno Setup (requires Windows)
    all         All targets buildable on the current platform
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


# ── helpers ───────────────────────────────────────────────────────────────────


def _run(*args: str, **kwargs) -> None:
    print(f"  $ {' '.join(args)}")
    subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def _version() -> str:
    sys.path.insert(0, str(ROOT))
    from fin._version import __version__

    return __version__


def _native_arch() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine == "arm64" else "intel"


# ── build steps ───────────────────────────────────────────────────────────────


def _pyinstaller() -> None:
    print("→ PyInstaller …")
    _run("uv", "run", "pyinstaller", "fin.spec", "--noconfirm")


def _dmg(arch: str, version: str) -> Path:
    if sys.platform != "darwin":
        print("DMG build requires macOS.", file=sys.stderr)
        sys.exit(1)

    if not shutil.which("create-dmg"):
        print("create-dmg not found. Run: brew install create-dmg", file=sys.stderr)
        sys.exit(1)

    dmg = DIST / f"Fin-{version}-{arch}.dmg"
    if dmg.exists():
        dmg.unlink()

    print(f"→ DMG ({arch}) …")
    _run(
        "create-dmg",
        "--volname",
        "Fin",
        "--window-pos",
        "200",
        "120",
        "--window-size",
        "600",
        "400",
        "--icon-size",
        "100",
        "--icon",
        "Fin.app",
        "175",
        "190",
        "--hide-extension",
        "Fin.app",
        "--app-drop-link",
        "425",
        "190",
        "--skip-jenkins",
        str(dmg),
        str(DIST / "Fin.app"),
    )
    return dmg


def _windows_installer(version: str) -> Path:
    if sys.platform != "win32":
        print("Windows installer build requires Windows.", file=sys.stderr)
        sys.exit(1)

    iscc = shutil.which("iscc")
    if not iscc:
        print(
            "iscc (Inno Setup) not found. Install from https://jrsoftware.org/isdl.php",
            file=sys.stderr,
        )
        sys.exit(1)

    print("→ Inno Setup installer …")
    _run(iscc, f"/DMyAppVersion={version}", str(ROOT / "installer" / "fin.iss"))
    return DIST / "installer" / f"Fin-Setup-{version}.exe"


# ── target dispatch ───────────────────────────────────────────────────────────


def build(targets: list[str], version: str) -> None:
    built: list[Path] = []

    needs_pyinstaller = any(
        t in ("mac", "mac-arm64", "mac-intel", "windows") for t in targets
    )
    if needs_pyinstaller:
        _pyinstaller()

    for target in targets:
        if target in ("mac", "mac-arm64"):
            arch = "arm64" if target == "mac-arm64" else _native_arch()
            built.append(_dmg(arch, version))

        elif target == "mac-intel":
            native = _native_arch()
            if native != "intel":
                print(
                    "Warning: building mac-intel on Apple Silicon — "
                    "binary may not run natively without Rosetta."
                )
            built.append(_dmg("intel", version))

        elif target == "windows":
            built.append(_windows_installer(version))

    print()
    for path in built:
        size_mb = path.stat().st_size / 1_048_576
        print(f"  ✓ {path.relative_to(ROOT)}  ({size_mb:.1f} MB)")


def _resolve_targets(raw: str) -> list[str]:
    if raw != "all":
        return [raw]
    if sys.platform == "darwin":
        return ["mac"]
    if sys.platform == "win32":
        return ["windows"]
    print(f"Unsupported platform: {sys.platform}", file=sys.stderr)
    sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Fin desktop installers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--target",
        default="mac",
        choices=["mac", "mac-arm64", "mac-intel", "windows", "all"],
        help="build target (default: mac)",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="version string for artifact name (default: latest git tag or 'dev')",
    )
    args = parser.parse_args()

    version = args.version or _version()
    targets = _resolve_targets(args.target)

    print(f"Building Fin {version}  targets={targets}")
    print()
    build(targets, version)


if __name__ == "__main__":
    main()
