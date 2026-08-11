"""SQLAlchemy engine, session, and UTC persistence foundations."""

from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative model base."""


class UTCDateTime(TypeDecorator[datetime]):
    """Persist aware UTC datetimes in SQLite and restore UTC on reads."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        del dialect
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


@lru_cache
def get_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


@lru_cache
def get_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(database_url),
        autoflush=False,
        expire_on_commit=False,
    )


def _ensure_sqlite_directory(database_url: str) -> None:
    url = make_url(database_url)
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
        return

    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def initialize_database() -> None:
    """Prepare storage and create metadata for currently registered models."""

    settings = get_settings()
    _ensure_sqlite_directory(settings.database_url)
    from app.models import post as post_models

    del post_models
    Base.metadata.create_all(bind=get_engine(settings.database_url))


def session_scope() -> Iterator[Session]:
    """Yield a database session using the current configured database."""

    settings = get_settings()
    with get_session_factory(settings.database_url)() as session:
        yield session
