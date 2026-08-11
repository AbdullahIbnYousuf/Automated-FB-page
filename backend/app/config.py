"""Typed application configuration with fail-closed publishing defaults."""

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
    database_url: str = f"sqlite:///{BACKEND_DIRECTORY / 'data' / 'app.db'}"
    frontend_origin: str = "http://127.0.0.1:5173"
    log_level: str = "INFO"
    upload_directory: Path = BACKEND_DIRECTORY / "data" / "uploads"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_image_pixels: int = 40_000_000

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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
