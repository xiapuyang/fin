import logging
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fin.api import app  # triggers setup_logging — must come before disable()
from fin.database import Base, get_db, import_all_models

# Suppress ERROR/WARNING noise from intentional mock failures in tests.
# setup_logging() registered a StreamHandler above; disable() silences it
# globally without touching production logging configuration.
logging.disable(logging.ERROR)


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import_all_models()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with (
        patch("fin.api.init_db"),
        patch("fin.api.warn_orphaned_bench_ids"),
        patch("fin.api.start_price_updater"),
        patch("fin.api.start_benchmark_backfill", return_value=lambda: None),
        patch("fin.api.stop_benchmark_backfill"),
    ):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
