"""Timezone conversion and DST edge-case tests."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.errors import AppError
from app.services.time_service import parse_local_schedule


def test_asia_dhaka_future_time_converts_to_aware_utc() -> None:
    local = datetime.now(ZoneInfo("Asia/Dhaka")) + timedelta(days=2)
    local = local.replace(second=0, microsecond=0)

    converted = parse_local_schedule(
        local.strftime("%Y-%m-%dT%H:%M"),
        "Asia/Dhaka",
    )

    assert converted.tzinfo is UTC
    assert converted == local.astimezone(UTC)


@pytest.mark.parametrize(
    "value",
    ["2027-03-14T02:30", "2027-11-07T01:30"],
)
def test_nonexistent_or_ambiguous_dst_time_is_rejected(value: str) -> None:
    with pytest.raises(AppError) as error:
        parse_local_schedule(value, "America/New_York")

    assert error.value.code == "INVALID_SCHEDULE"
