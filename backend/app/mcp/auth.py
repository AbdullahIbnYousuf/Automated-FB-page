"""Validate resource-bound Supabase OAuth JWTs against public signing keys."""

import time

import anyio
import httpx
import jwt
from mcp.server.auth.provider import AccessToken

from app.config import Settings


class SupabaseTokenVerifier:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport
        self._keys: dict[str, dict] = {}
        self._keys_until = 0.0
        self._refresh_after = 0.0
        self._lock = anyio.Lock()

    async def _key(self, kid: str) -> jwt.PyJWK | None:
        async with self._lock:
            now = time.monotonic()
            if now >= self._keys_until or (kid not in self._keys and now >= self._refresh_after):
                async with httpx.AsyncClient(
                    timeout=10, follow_redirects=False, trust_env=False, transport=self.transport,
                ) as client:
                    response = await client.get(
                        f"{self.settings.mcp_issuer_url}/.well-known/jwks.json"
                    )
                    response.raise_for_status()
                    self._keys = {
                        item["kid"]: item for item in response.json()["keys"]
                        if item.get("alg") in {"ES256", "RS256"} and item.get("kid")
                    }
                self._keys_until = now + 300
                self._refresh_after = now + 30
            key = self._keys.get(kid)
            return jwt.PyJWK.from_dict(key) if key else None

    async def verify_token(self, token: str) -> AccessToken | None:
        if len(token) > 16384:
            return None
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in {"ES256", "RS256"}:
                return None
            kid = header.get("kid")
            if not isinstance(kid, str):
                return None
            key = await self._key(kid)
            if key is None or key.algorithm_name != header["alg"]:
                return None
            claims = jwt.decode(
                token, key.key, algorithms=[key.algorithm_name],
                issuer=self.settings.mcp_issuer_url, audience=self.settings.mcp_resource_url,
                options={"require": ["iss", "aud", "exp", "iat", "sub", "email", "client_id", "scope"]},
            )
            if claims.get("role") != "authenticated" or claims.get("is_anonymous") is not False:
                return None
            email = claims["email"]
            client_id = claims["client_id"]
            scope = claims["scope"]
            if not isinstance(email, str) or not isinstance(client_id, str) or not client_id.strip():
                return None
            if not self.settings.operator_email or email.strip().lower() != self.settings.operator_email.strip().lower():
                return None
            if not isinstance(scope, str) or "email" not in scope.split():
                return None
            return AccessToken(
                token=token, client_id=client_id, scopes=scope.split(),
                expires_at=claims["exp"], subject=claims["sub"],
                resource=self.settings.mcp_resource_url,
                claims={"iss": claims["iss"], "email": email},
            )
        except (jwt.PyJWTError, httpx.HTTPError, KeyError, TypeError, ValueError, RuntimeError):
            # Never log the token or an exception that may contain its claims.
            return None
