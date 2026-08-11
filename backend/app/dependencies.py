"""FastAPI dependencies shared by protected resource routes."""

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import session_scope
from app.integrations.facebook.client import FacebookClient
from app.services.auth_service import AuthenticatedOperator, AuthService
from app.services.errors import AppError
from app.services.facebook_connection_service import FacebookConnectionService
from app.services.media_service import MediaService


bearer_scheme = HTTPBearer(auto_error=False)


def get_database_session() -> Iterator[Session]:
    yield from session_scope()


def get_auth_service(settings: Settings = Depends(get_settings)) -> AuthService:
    return AuthService(settings)


def get_media_service(settings: Settings = Depends(get_settings)) -> MediaService:
    return MediaService(settings)


@lru_cache
def get_facebook_connection_service() -> FacebookConnectionService:
    settings = get_settings()
    return FacebookConnectionService(settings, FacebookClient(settings))


async def require_operator(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedOperator:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            code="AUTH_REQUIRED",
            message="Sign in with the authorized operator account.",
            status_code=401,
        )
    return await auth_service.authenticate(credentials.credentials)
