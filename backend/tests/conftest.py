"""Isolated database, authentication, and private-storage test fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import get_engine, get_session_factory
from app.dependencies import get_media_service, require_operator
from app.main import app
from app.services.auth_service import AuthenticatedOperator
from app.services.errors import AppError
from app.services.media_service import MediaService, StoredImage, StoredObject


ENVIRONMENT_KEYS = (
    "APPLICATION_MODE",
    "AUTOMATION_ENABLED",
    "PUBLISH_MODE",
    "APP_TIMEZONE",
    "DATABASE_URL",
    "FRONTEND_ORIGINS",
    "MAX_UPLOAD_BYTES",
    "MAX_IMAGE_PIXELS",
    "AUTH_REQUIRED",
    "OPERATOR_EMAIL",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_STORAGE_BUCKET",
    "FACEBOOK_GRAPH_API_VERSION",
    "FACEBOOK_PAGE_ID",
    "FACEBOOK_PAGE_ACCESS_TOKEN",
)


class InMemoryMediaService:
    def __init__(self, settings: Settings) -> None:
        self.validator = MediaService(settings)
        self.objects: dict[str, StoredObject] = {}

    async def store_upload(self, upload) -> StoredImage:  # type: ignore[no-untyped-def]
        content, extension, mime_type, display_name = await self.validator._validate_upload(
            upload
        )
        from uuid import uuid4

        object_path = f"posts/{uuid4()}{extension}"
        if object_path in self.objects:
            raise AppError(
                code="IMAGE_STORAGE_CONFLICT",
                message="The image could not be stored safely. Try again.",
                status_code=409,
            )
        self.objects[object_path] = StoredObject(content=content, mime_type=mime_type)
        return StoredImage(
            object_path=object_path,
            mime_type=mime_type,
            original_filename=display_name or f"upload{extension}",
        )

    async def get_object(self, object_path: str) -> StoredObject:
        MediaService.validate_object_path(object_path)
        try:
            return self.objects[object_path]
        except KeyError as exc:
            raise AppError(
                code="MEDIA_NOT_FOUND", message="Image not found.", status_code=404
            ) from exc

    async def object_exists(self, object_path: str) -> bool:
        return object_path in self.objects

    async def delete_object(self, object_path: str) -> None:
        self.objects.pop(object_path, None)


async def authenticated_operator() -> AuthenticatedOperator:
    return AuthenticatedOperator(id="operator-id", email="operator@example.com")


@pytest.fixture(autouse=True)
def isolated_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> Iterator[None]:  # type: ignore[no-untyped-def]
    for key in ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APPLICATION_MODE", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("OPERATOR_EMAIL", "operator@example.com")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "test-publishable-key")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-secret-key")
    get_settings.cache_clear()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    yield
    settings = get_settings()
    get_engine(settings.require_database_url()).dispose()
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    get_session_factory.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
def fake_media() -> InMemoryMediaService:
    return InMemoryMediaService(get_settings())


@pytest.fixture
def client(fake_media: InMemoryMediaService) -> Iterator[TestClient]:
    app.dependency_overrides[get_media_service] = lambda: fake_media
    app.dependency_overrides[require_operator] = authenticated_operator
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def unauthenticated_client(fake_media: InMemoryMediaService) -> Iterator[TestClient]:
    app.dependency_overrides[get_media_service] = lambda: fake_media
    with TestClient(app) as test_client:
        yield test_client
