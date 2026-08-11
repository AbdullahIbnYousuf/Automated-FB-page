"""Supabase Auth token verification for the single authorized operator."""

from dataclasses import dataclass

import httpx

from app.config import Settings
from app.services.errors import AppError


@dataclass(frozen=True)
class AuthenticatedOperator:
    id: str
    email: str


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def authenticate(self, access_token: str) -> AuthenticatedOperator:
        if not access_token.strip():
            raise self._unauthorized()

        try:
            url = f"{self.settings.require_supabase_url()}/auth/v1/user"
            publishable_key = self.settings.require_supabase_publishable_key()
            async with httpx.AsyncClient(
                timeout=self.settings.supabase_request_timeout_seconds
            ) as client:
                response = await client.get(
                    url,
                    headers={
                        "apikey": publishable_key,
                        "Authorization": f"Bearer {access_token}",
                    },
                )
        except (httpx.HTTPError, RuntimeError) as exc:
            raise AppError(
                code="AUTH_UNAVAILABLE",
                message="Authentication is temporarily unavailable.",
                status_code=503,
            ) from exc

        if response.status_code != 200:
            raise self._unauthorized()

        try:
            payload = response.json()
            user_id = str(payload["id"])
            email = str(payload["email"]).strip().lower()
        except (KeyError, TypeError, ValueError) as exc:
            raise self._unauthorized() from exc

        allowed_email = (self.settings.operator_email or "").strip().lower()
        if not allowed_email or email != allowed_email:
            raise AppError(
                code="OPERATOR_FORBIDDEN",
                message="This account is not authorized for this dashboard.",
                status_code=403,
            )
        return AuthenticatedOperator(id=user_id, email=email)

    @staticmethod
    def _unauthorized() -> AppError:
        return AppError(
            code="AUTH_REQUIRED",
            message="Sign in with the authorized operator account.",
            status_code=401,
        )
