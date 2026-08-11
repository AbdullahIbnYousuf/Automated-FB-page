"""Typed application configuration with fail-closed hosted defaults."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIRECTORY.parent


class PublishMode(StrEnum):
    """Supported publishing modes.

    Adding a new value must be an intentional product and safety decision.
    """

    DRY_RUN = "dry_run"
    FACEBOOK_SCHEDULE = "facebook_schedule"


class Settings(BaseSettings):
    """Environment-backed settings loaded only by the backend."""

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    application_name: str = "Facebook Page Operations Dashboard"
    application_mode: str = "development"
    automation_enabled: bool = False
    publish_mode: PublishMode = PublishMode.DRY_RUN
    app_timezone: str = "Asia/Dhaka"
    database_url: str | None = None
    frontend_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    log_level: str = "INFO"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_image_pixels: int = 40_000_000

    auth_required: bool = True
    operator_email: str | None = None
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_secret_key: SecretStr | None = None
    supabase_storage_bucket: str = "post-images"
    supabase_request_timeout_seconds: float = 15.0

    facebook_graph_api_version: str = "v26.0"
    facebook_page_id: str | None = None
    facebook_page_access_token: SecretStr | None = None

    @property
    def publishing_enabled(self) -> bool:
        """Return true only when both required real-write switches are enabled."""

        return (
            self.automation_enabled
            and self.publish_mode is PublishMode.FACEBOOK_SCHEDULE
        )

    @property
    def facebook_page_id_configured(self) -> bool:
        return bool(self.facebook_page_id and self.facebook_page_id.strip())

    @property
    def facebook_token_configured(self) -> bool:
        if self.facebook_page_access_token is None:
            return False
        return bool(self.facebook_page_access_token.get_secret_value().strip())

    @property
    def allowed_frontend_origins(self) -> list[str]:
        """Return explicit CORS origins without allowing wildcards."""

        return [
            origin.strip().rstrip("/")
            for origin in self.frontend_origins.split(",")
            if origin.strip() and origin.strip() != "*"
        ]

    @property
    def supabase_configured(self) -> bool:
        return all(
            (
                self.supabase_url and self.supabase_url.strip(),
                self.supabase_publishable_key
                and self.supabase_publishable_key.get_secret_value().strip(),
                self.supabase_secret_key
                and self.supabase_secret_key.get_secret_value().strip(),
                self.operator_email and self.operator_email.strip(),
            )
        )

    def require_database_url(self) -> str:
        if not self.database_url or not self.database_url.strip():
            raise RuntimeError("DATABASE_URL must be configured.")
        value = self.database_url.strip()
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    def require_supabase_url(self) -> str:
        if not self.supabase_url or not self.supabase_url.strip():
            raise RuntimeError("SUPABASE_URL must be configured.")
        return self.supabase_url.strip().rstrip("/")

    def require_supabase_publishable_key(self) -> str:
        if self.supabase_publishable_key is None:
            raise RuntimeError("SUPABASE_PUBLISHABLE_KEY must be configured.")
        value = self.supabase_publishable_key.get_secret_value().strip()
        if not value:
            raise RuntimeError("SUPABASE_PUBLISHABLE_KEY must be configured.")
        return value

    def require_supabase_secret_key(self) -> str:
        if self.supabase_secret_key is None:
            raise RuntimeError("SUPABASE_SECRET_KEY must be configured.")
        value = self.supabase_secret_key.get_secret_value().strip()
        if not value:
            raise RuntimeError("SUPABASE_SECRET_KEY must be configured.")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
