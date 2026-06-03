"""App metadata: version, repo URL, license. Read-only, no auth needed."""

from fastapi import APIRouter

from fin._version import __version__

router = APIRouter(prefix="/api/meta", tags=["meta"])

_GITHUB_REPO = "xiapuyang/fin"


@router.get("")
def get_meta() -> dict:
    """Return app version and links for the About page / sidebar."""
    return {
        "version": __version__,
        "repo": _GITHUB_REPO,
        "repo_url": f"https://github.com/{_GITHUB_REPO}",
        "releases_url": f"https://github.com/{_GITHUB_REPO}/releases/latest",
        "license": "MIT",
        "license_url": f"https://github.com/{_GITHUB_REPO}/blob/main/LICENSE",
    }
