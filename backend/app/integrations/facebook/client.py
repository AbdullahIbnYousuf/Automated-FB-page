"""Narrow client for Page identity reads and one scheduled-photo write."""

import re
from collections.abc import Mapping

import httpx

from app.config import Settings
from app.integrations.facebook.errors import (
    FacebookClientError,
    FacebookWriteError,
    FacebookWriteErrorCode,
)
from app.integrations.facebook.schemas import (
    FacebookConnectionState,
    FacebookPageIdentity,
    FacebookScheduledPhoto,
)


_API_VERSION_PATTERN = re.compile(r"^v\d+\.\d+$")
_PAGE_ID_PATTERN = re.compile(r"^\d+$")
_EXPIRED_TOKEN_SUBCODES = frozenset({463, 467})
_PERMISSION_ERROR_CODES = frozenset({10, 200, 294, 299})
_TRANSIENT_ERROR_CODES = frozenset({1, 2, 4, 17, 32, 341, 613})
_RATE_LIMIT_ERROR_CODES = frozenset({4, 17, 32, 341, 613})


class FacebookClient:
    """Own all versioned Meta requests and secret-bearing authorization."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def get_page_identity(self) -> FacebookPageIdentity:
        api_version, page_id, token = self.configuration()

        try:
            async with httpx.AsyncClient(
                base_url="https://graph.facebook.com",
                timeout=httpx.Timeout(
                    self._settings.facebook_request_timeout_seconds
                ),
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    f"/{api_version}/{page_id}",
                    params={"fields": "id,name"},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise FacebookClientError(
                state=FacebookConnectionState.META_UNAVAILABLE,
                safe_message="Meta did not respond before the connection test timed out.",
            ) from exc
        except httpx.RequestError as exc:
            raise FacebookClientError(
                state=FacebookConnectionState.META_UNAVAILABLE,
                safe_message="Meta is temporarily unreachable from the backend.",
            ) from exc

        if response.status_code >= 400:
            raise self._safe_response_error(response)

        try:
            payload = response.json()
            returned_id = str(payload["id"]).strip()
            page_name = str(payload["name"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise FacebookClientError(
                state=FacebookConnectionState.MALFORMED_RESPONSE,
                safe_message="Meta returned an unexpected Page response.",
            ) from exc

        if not returned_id or not page_name:
            raise FacebookClientError(
                state=FacebookConnectionState.MALFORMED_RESPONSE,
                safe_message="Meta returned an incomplete Page response.",
            )
        if returned_id != page_id:
            raise FacebookClientError(
                state=FacebookConnectionState.PAGE_MISMATCH,
                safe_message="Meta returned a different Page than the configured Page ID.",
            )
        return FacebookPageIdentity(id=returned_id, name=page_name)

    async def schedule_page_photo(
        self,
        *,
        caption: str,
        image_content: bytes,
        image_mime_type: str,
        scheduled_publish_time: int,
    ) -> FacebookScheduledPhoto:
        """Issue exactly one multipart scheduled-photo request without retries."""

        api_version, page_id, token = self.configuration(for_write=True)
        extension = "jpg" if image_mime_type == "image/jpeg" else "png"
        try:
            async with httpx.AsyncClient(
                base_url="https://graph.facebook.com",
                timeout=httpx.Timeout(self._settings.facebook_request_timeout_seconds),
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"/{api_version}/{page_id}/photos",
                    data={
                        "caption": caption,
                        "published": "false",
                        "scheduled_publish_time": str(scheduled_publish_time),
                        "unpublished_content_type": "SCHEDULED",
                    },
                    files={
                        "source": (
                            f"scheduled-photo.{extension}",
                            image_content,
                            image_mime_type,
                        )
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise FacebookWriteError(
                code=FacebookWriteErrorCode.OUTCOME_UNKNOWN,
                safe_message=(
                    "Facebook scheduling outcome is unknown. The request may have "
                    "reached Meta; do not submit this post again until it is checked."
                ),
                outcome_unknown=True,
            ) from exc

        if response.status_code >= 400:
            raise self._safe_write_response_error(response)

        try:
            payload = response.json()
            photo_id = str(payload["id"]).strip()
            raw_post_id = payload.get("post_id")
            post_id = str(raw_post_id).strip() if raw_post_id is not None else None
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise FacebookWriteError(
                code=FacebookWriteErrorCode.OUTCOME_UNKNOWN,
                safe_message=(
                    "Facebook scheduling outcome is unknown because Meta returned no "
                    "usable identifier. Check Meta before any further action."
                ),
                outcome_unknown=True,
            ) from exc
        if not photo_id or post_id == "":
            raise FacebookWriteError(
                code=FacebookWriteErrorCode.OUTCOME_UNKNOWN,
                safe_message=(
                    "Facebook scheduling outcome is unknown because Meta returned no "
                    "usable identifier. Check Meta before any further action."
                ),
                outcome_unknown=True,
            )
        return FacebookScheduledPhoto(id=photo_id, post_id=post_id)

    def configuration(self, *, for_write: bool = False) -> tuple[str, str, str]:
        api_version = self._settings.facebook_graph_api_version.strip()
        page_id = (self._settings.facebook_page_id or "").strip()
        token = (
            self._settings.facebook_page_access_token.get_secret_value().strip()
            if self._settings.facebook_page_access_token is not None
            else ""
        )
        try:
            self._validate_configuration(api_version, page_id, token)
        except FacebookClientError as exc:
            if not for_write:
                raise
            raise FacebookWriteError(
                code=FacebookWriteErrorCode.CONFIGURATION,
                safe_message="Facebook Page publishing is not fully configured.",
            ) from exc
        return api_version, page_id, token

    @staticmethod
    def _validate_configuration(api_version: str, page_id: str, token: str) -> None:
        if not api_version or not _API_VERSION_PATTERN.fullmatch(api_version):
            raise FacebookClientError(
                state=FacebookConnectionState.INVALID_CONFIGURATION,
                safe_message="The configured Graph API version is invalid.",
            )
        if not page_id or not _PAGE_ID_PATTERN.fullmatch(page_id):
            raise FacebookClientError(
                state=FacebookConnectionState.INVALID_CONFIGURATION,
                safe_message="The configured Facebook Page ID is invalid.",
            )
        if not token:
            raise FacebookClientError(
                state=FacebookConnectionState.NOT_CONFIGURED,
                safe_message="The Facebook Page connection is not fully configured.",
            )

    @classmethod
    def _safe_response_error(cls, response: httpx.Response) -> FacebookClientError:
        error_code, error_subcode = cls._extract_error_codes(response)

        if error_code == 190:
            if error_subcode in _EXPIRED_TOKEN_SUBCODES:
                return FacebookClientError(
                    state=FacebookConnectionState.EXPIRED_CREDENTIALS,
                    safe_message="The Facebook Page access token has expired.",
                    meta_error_code=error_code,
                )
            return FacebookClientError(
                state=FacebookConnectionState.INVALID_CREDENTIALS,
                safe_message="Meta did not accept the Facebook Page access token.",
                meta_error_code=error_code,
            )
        if error_code in _PERMISSION_ERROR_CODES:
            return FacebookClientError(
                state=FacebookConnectionState.INSUFFICIENT_ACCESS,
                safe_message="The token does not have access to read the configured Page.",
                meta_error_code=error_code,
            )
        if response.status_code == 404 or error_code == 100:
            return FacebookClientError(
                state=FacebookConnectionState.PAGE_INACCESSIBLE,
                safe_message="The configured Facebook Page is not accessible with this token.",
                meta_error_code=error_code,
            )
        if (
            response.status_code >= 500
            or response.status_code == 429
            or error_code in _TRANSIENT_ERROR_CODES
        ):
            return FacebookClientError(
                state=FacebookConnectionState.META_UNAVAILABLE,
                safe_message="Meta could not complete the connection test right now.",
                meta_error_code=error_code,
            )
        return FacebookClientError(
            state=FacebookConnectionState.ERROR,
            safe_message="Facebook Page connection verification failed safely.",
            meta_error_code=error_code,
        )

    @staticmethod
    def _extract_error_codes(response: httpx.Response) -> tuple[int | None, int | None]:
        try:
            payload = response.json()
            error = payload.get("error") if isinstance(payload, Mapping) else None
            if not isinstance(error, Mapping):
                return None, None
            code = error.get("code")
            subcode = error.get("error_subcode")
            return (
                code if isinstance(code, int) else None,
                subcode if isinstance(subcode, int) else None,
            )
        except (TypeError, ValueError):
            return None, None

    @classmethod
    def _safe_write_response_error(cls, response: httpx.Response) -> FacebookWriteError:
        error_code, error_subcode = cls._extract_error_codes(response)
        if error_code == 190:
            if error_subcode in _EXPIRED_TOKEN_SUBCODES:
                return FacebookWriteError(
                    code=FacebookWriteErrorCode.EXPIRED_CREDENTIALS,
                    safe_message="The Facebook Page access token has expired.",
                    meta_error_code=error_code,
                )
            return FacebookWriteError(
                code=FacebookWriteErrorCode.INVALID_CREDENTIALS,
                safe_message="Meta did not accept the Facebook Page access token.",
                meta_error_code=error_code,
            )
        if error_code in _PERMISSION_ERROR_CODES:
            return FacebookWriteError(
                code=FacebookWriteErrorCode.PERMISSION_DENIED,
                safe_message="The Page token cannot create posts for this Page.",
                meta_error_code=error_code,
            )
        if error_code == 324:
            return FacebookWriteError(
                code=FacebookWriteErrorCode.INVALID_IMAGE,
                safe_message="Meta rejected the image file.",
                meta_error_code=error_code,
            )
        if error_code == 100:
            return FacebookWriteError(
                code=FacebookWriteErrorCode.INVALID_SCHEDULE,
                safe_message="Meta rejected the scheduled time or request parameters.",
                meta_error_code=error_code,
            )
        if error_code == 368:
            return FacebookWriteError(
                code=FacebookWriteErrorCode.UNSUPPORTED_REQUEST,
                safe_message="Meta does not allow this Page photo request.",
                meta_error_code=error_code,
            )
        if error_code in _RATE_LIMIT_ERROR_CODES or response.status_code == 429:
            return FacebookWriteError(
                code=FacebookWriteErrorCode.RATE_LIMITED,
                safe_message="Meta rate-limited the Page scheduling request.",
                meta_error_code=error_code,
            )
        if response.status_code == 404:
            return FacebookWriteError(
                code=FacebookWriteErrorCode.PAGE_INACCESSIBLE,
                safe_message="The configured Facebook Page is not accessible.",
                meta_error_code=error_code,
            )
        if response.status_code >= 500 or error_code in {1, 2}:
            return FacebookWriteError(
                code=FacebookWriteErrorCode.META_UNAVAILABLE,
                safe_message="Meta could not accept the scheduling request right now.",
                meta_error_code=error_code,
            )
        return FacebookWriteError(
            code=FacebookWriteErrorCode.REJECTED,
            safe_message="Facebook rejected the scheduling request.",
            meta_error_code=error_code,
        )
