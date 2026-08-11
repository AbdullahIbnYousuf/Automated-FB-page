"""SQLAlchemy engine, session, and UTC persistence foundations."""

from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative model base."""


class UTCDateTime(TypeDecorator[datetime]):
    """Persist aware UTC datetimes and normalize reads to UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        normalized = value.astimezone(UTC)
        if dialect.name == "sqlite":
            return normalized.replace(tzinfo=None)
        return normalized

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


@lru_cache
def get_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=not database_url.startswith("sqlite"),
    )


@lru_cache
def get_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(database_url),
        autoflush=False,
        expire_on_commit=False,
    )


def initialize_database() -> None:
    """Validate connectivity; hosted schema changes are applied by migrations."""

    settings = get_settings()
    database_url = settings.require_database_url()
    if database_url.startswith("sqlite"):
        from app.models import post as post_models

        del post_models
        Base.metadata.create_all(bind=get_engine(database_url))
    with get_engine(database_url).connect() as connection:
        connection.execute(text("SELECT 1"))


def session_scope() -> Iterator[Session]:
    """Yield a database session using the current configured database."""

    settings = get_settings()
    with get_session_factory(settings.require_database_url())() as session:
        yield session
