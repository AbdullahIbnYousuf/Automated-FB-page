"""Small structured-logging setup using the Python standard library."""

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Serialize application log records without request bodies or secrets."""

    _safe_extra_fields = (
        "event",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "application_mode",
        "publish_mode",
        "automation_enabled",
        "post_id",
        "attempt_id",
        "result",
        "external_request_made",
        "facebook_status",
        "meta_error_code",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._safe_extra_fields:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Configure root application logging once at startup."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
