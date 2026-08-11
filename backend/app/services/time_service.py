"""Explicit IANA-timezone parsing and UTC conversion."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.errors import AppError


def parse_local_schedule(
    value: str,
    timezone_name: str,
    *,
    now: datetime | None = None,
) -> datetime:
    try:
        local_value = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AppError(
            code="INVALID_SCHEDULE",
            message="Enter a valid future date and time.",
            status_code=422,
        ) from exc

    if local_value.tzinfo is not None or local_value.utcoffset() is not None:
        raise AppError(
            code="INVALID_SCHEDULE",
            message="Schedule input must be a local date and time without an offset.",
            status_code=422,
        )

    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise AppError(
            code="INVALID_TIMEZONE",
            message="The configured application timezone is invalid.",
            status_code=500,
        ) from exc

    first = local_value.replace(tzinfo=timezone, fold=0)
    second = local_value.replace(tzinfo=timezone, fold=1)
    first_round_trip = first.astimezone(UTC).astimezone(timezone).replace(tzinfo=None)
    second_round_trip = second.astimezone(UTC).astimezone(timezone).replace(tzinfo=None)
    first_valid = first_round_trip == local_value
    second_valid = second_round_trip == local_value

    if not first_valid and not second_valid:
        raise AppError(
            code="INVALID_SCHEDULE",
            message="That local time does not exist in the configured timezone.",
            status_code=422,
        )

    if (
        first_valid
        and second_valid
        and first.utcoffset() != second.utcoffset()
    ):
        raise AppError(
            code="INVALID_SCHEDULE",
            message="That local time is ambiguous in the configured timezone.",
            status_code=422,
        )

    aware_local = first if first_valid else second
    scheduled_utc = aware_local.astimezone(UTC)
    current_utc = (now or datetime.now(UTC)).astimezone(UTC)
    if scheduled_utc <= current_utc:
        raise AppError(
            code="INVALID_SCHEDULE",
            message="Schedule time must be in the future.",
            status_code=422,
        )

    return scheduled_utc


def utc_to_local_iso(value: datetime, timezone_name: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Stored schedule timestamp must be timezone-aware")
    return value.astimezone(ZoneInfo(timezone_name)).isoformat(timespec="minutes")
