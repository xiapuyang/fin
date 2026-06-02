"""Download CDN-hosted frontend assets into frontend/vendor/ for offline use.

Run: ``uv run python scripts/vendor_frontend.py``

Idempotent: existing files are skipped unless --force is passed. Each file is
size-validated after download to catch truncated responses.
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

VENDOR_DIR = Path(__file__).parent.parent / "frontend" / "vendor"
FONTS_DIR = VENDOR_DIR / "fonts"

JS_ASSETS = [
    (
        "https://unpkg.com/react@18.3.1/umd/react.production.min.js",
        "react.production.min.js",
        5_000,  # ~10KB — React core is intentionally small in production build
    ),
    (
        "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js",
        "react-dom.production.min.js",
        100_000,  # ~120KB
    ),
    (
        "https://unpkg.com/@babel/standalone@7.29.0/babel.min.js",
        "babel.min.js",
        500_000,  # ~900KB
    ),
]

FONT_CSS_URLS = [
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap",
    "https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;700;900&display=swap",
]

_WOFF2_RE = re.compile(r"url\(([^)]+\.woff2)\)")
_MIN_WOFF2_SIZE = 1_000


def _fetch(url: str, dest: Path, min_size: int, force: bool) -> bool:
    """Download url to dest. Returns True if downloaded, False if skipped."""
    if dest.exists() and not force:
        if dest.stat().st_size >= min_size:
            print(f"  skip  {dest.name}")
            return False
        print(f"  re-download (truncated)  {dest.name}")

    print(f"  fetch {url}")
    headers = {"User-Agent": "fin-vendor/1.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    if len(data) < min_size:
        print(f"  ERROR: {dest.name} only {len(data)} bytes (expected ≥{min_size})")
        sys.exit(1)

    dest.write_bytes(data)
    print(f"  wrote {dest.name}  ({len(data):,} bytes)")
    return True


def _download_fonts(force: bool) -> str:
    """Download font CSS + woff2 files; return merged local CSS."""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    combined_css_parts: list[str] = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }

    for css_url in FONT_CSS_URLS:
        print(f"  fetch font CSS {css_url}")
        req = urllib.request.Request(css_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            css_text = resp.read().decode("utf-8")

        woff2_urls = _WOFF2_RE.findall(css_text)
        for woff2_url in woff2_urls:
            filename = woff2_url.split("/")[-1].split("?")[0]
            dest = FONTS_DIR / filename
            _fetch(woff2_url, dest, _MIN_WOFF2_SIZE, force)
            css_text = css_text.replace(woff2_url, f"./{filename}")

        combined_css_parts.append(css_text)

    return "\n".join(combined_css_parts)


def main(force: bool = False) -> None:
    """Download all vendor assets."""
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    print("=== JS assets ===")
    for url, filename, min_size in JS_ASSETS:
        _fetch(url, VENDOR_DIR / filename, min_size, force)

    print("\n=== Fonts ===")
    fonts_css_dest = FONTS_DIR / "fonts.css"
    if fonts_css_dest.exists() and not force:
        print("  skip  fonts.css (delete to re-download fonts)")
    else:
        merged_css = _download_fonts(force)
        fonts_css_dest.write_text(merged_css, encoding="utf-8")
        print("  wrote fonts.css")

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Re-download existing files"
    )
    args = parser.parse_args()
    main(force=args.force)
