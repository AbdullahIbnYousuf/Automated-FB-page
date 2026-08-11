"""Deterministic local-only scheduling adapter."""

from dataclasses import dataclass

from app.models.post import Post


@dataclass(frozen=True)
class DryRunResult:
    success: bool
    message: str
    external_request_made: bool = False


class DryRunScheduler:
    """Simulate acceptance without invoking any network or provider client."""

    def schedule(self, post: Post) -> DryRunResult:
        del post
        return DryRunResult(
            success=True,
            message="Dry-run scheduling completed. No request was sent to Facebook.",
        )
