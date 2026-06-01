import sys
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from snapshot_resolver import find_by_date, create


def test_find_by_date_returns_existing():
    snapshots = [
        {"id": 1, "snapshot_date": "2026-05-30", "label": "may-end"},
        {"id": 2, "snapshot_date": "2026-05-31", "label": "today"},
    ]
    with patch("snapshot_resolver._fetch_all", return_value=snapshots):
        result = find_by_date("2026-05-31")
        assert result == {"id": 2, "snapshot_date": "2026-05-31", "label": "today"}


def test_find_by_date_returns_none_if_missing():
    with patch("snapshot_resolver._fetch_all", return_value=[]):
        assert find_by_date("2026-05-31") is None


def test_create_posts_and_returns_id():
    fake_post = Mock()
    fake_post.return_value.status_code = 201
    fake_post.return_value.json.return_value = {
        "id": 42,
        "snapshot_date": "2026-05-31",
        "label": "import",
    }
    with patch("snapshot_resolver.requests.post", fake_post):
        result = create("2026-05-31", "import")
        assert result["id"] == 42
        fake_post.assert_called_once()
        call_kwargs = fake_post.call_args.kwargs
        assert call_kwargs["json"] == {
            "snapshot_date": "2026-05-31",
            "label": "import",
        }
