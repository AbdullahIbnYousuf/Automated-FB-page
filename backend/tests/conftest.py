"""Isolated SQLite and upload storage for every backend test."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_engine, get_session_factory
from app.main import app


ENVIRONMENT_KEYS = (
    "APPLICATION_MODE",
    "AUTOMATION_ENABLED",
    "PUBLISH_MODE",
    "APP_TIMEZONE",
    "DATABASE_URL",
    "UPLOAD_DIRECTORY",
    "MAX_UPLOAD_BYTES",
    "MAX_IMAGE_PIXELS",
    "FACEBOOK_GRAPH_API_VERSION",
    "FACEBOOK_PAGE_ID",
    "FACEBOOK_PAGE_ACCESS_TOKEN",
)


@pytest.fixture(autouse=True)
def isolated_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> Iterator[None]:  # type: ignore[no-untyped-def]
    for key in ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    yield
    settings = get_settings()
    get_engine(settings.database_url).dispose()
    get_settings.cache_clear()
    get_session_factory.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
