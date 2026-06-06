"""Tests for fin/data_migration.py."""

from pathlib import Path

from fin.data_migration import migrate_data_dir


def _make_data_dir(path: Path, files: list[str] | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name in files or ["fin.db", "settings.json", "market_state.json"]:
        (path / name).write_bytes(b"data:" + name.encode())
    return path


class TestUserOverride:
    def test_skips_when_fin_data_dir_is_set(self, tmp_path, monkeypatch):
        home_fin = tmp_path / ".fin"
        _make_data_dir(home_fin / "data")
        new_dir = tmp_path / "custom"
        new_dir.mkdir()
        monkeypatch.setenv("FIN_DATA_DIR", str(new_dir))

        result = migrate_data_dir(new_dir, home_fin, tmp_path / "project")

        assert result is False
        assert not (new_dir / "fin.db").exists()


class TestNoMigrationNeeded:
    def test_skips_when_new_data_dir_already_has_db(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        new_dir = _make_data_dir(tmp_path / "new")
        _make_data_dir(tmp_path / "old")
        assert (
            migrate_data_dir(new_dir, tmp_path / "home_fin", tmp_path / "project")
            is False
        )

    def test_skips_when_no_legacy_db_exists(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        new_dir = tmp_path / "new"
        new_dir.mkdir()
        assert (
            migrate_data_dir(new_dir, tmp_path / "home_fin", tmp_path / "project")
            is False
        )

    def test_skips_when_legacy_dir_equals_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        # home_fin/data IS the current DATA_DIR — nothing to migrate
        home_fin = tmp_path / ".fin"
        data_dir = home_fin / "data"
        _make_data_dir(data_dir)
        assert migrate_data_dir(data_dir, home_fin, tmp_path / "project") is False


class TestMigrationFromHomeFin:
    def test_copies_files_to_new_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        home_fin = tmp_path / ".fin"
        _make_data_dir(home_fin / "data")
        new_dir = tmp_path / "AppData" / "Fin" / "Fin"
        new_dir.mkdir(parents=True)

        result = migrate_data_dir(new_dir, home_fin, tmp_path / "project")

        assert result is True
        assert (new_dir / "fin.db").exists()
        assert (new_dir / "settings.json").exists()
        assert (new_dir / "market_state.json").exists()

    def test_legacy_dir_is_preserved(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        home_fin = tmp_path / ".fin"
        _make_data_dir(home_fin / "data")
        new_dir = tmp_path / "AppData" / "Fin" / "Fin"
        new_dir.mkdir(parents=True)

        migrate_data_dir(new_dir, home_fin, tmp_path / "project")

        assert (home_fin / "data" / "fin.db").exists()

    def test_file_contents_are_preserved(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        home_fin = tmp_path / ".fin"
        legacy = home_fin / "data"
        legacy.mkdir(parents=True)
        (legacy / "fin.db").write_bytes(b"original content")

        new_dir = tmp_path / "AppData" / "Fin" / "Fin"
        new_dir.mkdir(parents=True)

        migrate_data_dir(new_dir, home_fin, tmp_path / "project")

        assert (new_dir / "fin.db").read_bytes() == b"original content"

    def test_creates_new_data_dir_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        home_fin = tmp_path / ".fin"
        _make_data_dir(home_fin / "data")
        new_dir = tmp_path / "AppData" / "Fin" / "Fin"
        # new_dir intentionally not created

        migrate_data_dir(new_dir, home_fin, tmp_path / "project")

        assert new_dir.exists()
        assert (new_dir / "fin.db").exists()


class TestMigrationFromProjectRoot:
    def test_copies_files_from_project_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        project = tmp_path / "fin"
        _make_data_dir(project / "data")
        new_dir = tmp_path / ".fin" / "data"
        new_dir.mkdir(parents=True)

        result = migrate_data_dir(new_dir, tmp_path / ".fin", project)

        assert result is True
        assert (new_dir / "fin.db").exists()

    def test_home_fin_takes_priority_over_project_root(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        home_fin = tmp_path / ".fin"
        _make_data_dir(home_fin / "data", files=["fin.db", "from_home.json"])
        project = tmp_path / "fin"
        _make_data_dir(project / "data", files=["fin.db", "from_project.json"])
        new_dir = tmp_path / "AppData" / "Fin" / "Fin"
        new_dir.mkdir(parents=True)

        migrate_data_dir(new_dir, home_fin, project)

        assert (new_dir / "from_home.json").exists()
        assert not (new_dir / "from_project.json").exists()


class TestIdempotency:
    def test_does_not_migrate_twice(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        home_fin = tmp_path / ".fin"
        _make_data_dir(home_fin / "data")
        new_dir = tmp_path / "AppData" / "Fin" / "Fin"
        new_dir.mkdir(parents=True)

        first = migrate_data_dir(new_dir, home_fin, tmp_path / "project")
        second = migrate_data_dir(new_dir, home_fin, tmp_path / "project")

        assert first is True
        assert second is False

    def test_does_not_overwrite_existing_files(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIN_DATA_DIR", raising=False)
        home_fin = tmp_path / ".fin"
        legacy = home_fin / "data"
        legacy.mkdir(parents=True)
        (legacy / "fin.db").write_bytes(b"old")

        new_dir = tmp_path / "AppData" / "Fin" / "Fin"
        new_dir.mkdir(parents=True)
        (new_dir / "fin.db").write_bytes(b"new")

        migrate_data_dir(new_dir, home_fin, tmp_path / "project")

        assert (new_dir / "fin.db").read_bytes() == b"new"
