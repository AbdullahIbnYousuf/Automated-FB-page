"""FastAPI dependencies shared by resource routes."""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.database import session_scope


def get_database_session() -> Iterator[Session]:
    yield from session_scope()
