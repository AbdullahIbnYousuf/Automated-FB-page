"""Thin MCP tools over the existing application services."""

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import get_session_factory
from app.integrations.facebook.client import FacebookClient
from app.integrations.facebook.schemas import FacebookConnectionStatus
from app.mcp.files import ChatGPTFileDownloader
from app.mcp.schemas import (
    CreateAndScheduleInput, CreatePostInput, EmptyInput, ListPostsInput,
    PostAndSchedule, PostInput, PostPage, PostSummary, SchedulePostInput,
    ToolError, ToolOutput, UpdatePostInput,
)
from app.models.mcp_operation import McpOperation
from app.models.post import SchedulingMode
from app.schemas.post import PostResponse, PostUpdateRequest, ScheduleResponse
from app.services.errors import AppError
from app.services.facebook_connection_service import FacebookConnectionService
from app.services.media_service import MediaService
from app.services.post_creation_service import create_post_from_upload
from app.services.post_service import PostService
from app.services.scheduling_service import SchedulingService
from app.services.system_status_service import SystemStatusResponse, system_status


CONTRACTS: dict[str, tuple[type[BaseModel], Any, str]] = {
    "get_system_status": (EmptyInput, SystemStatusResponse, "Read configuration, server time and the real-publishing gates. Credentials are never returned."),
    "test_facebook_connection": (EmptyInput, FacebookConnectionStatus, "Test read-only access to the configured Facebook Page. This does not prove scheduling permission."),
    "list_posts": (ListPostsInput, PostPage, "List saved post summaries, with optional status filter and pagination."),
    "get_post": (PostInput, PostResponse, "Read one saved post and its scheduling history. A scheduled status does not prove publication."),
    "create_post": (CreatePostInput, PostResponse, "Save a draft with the user's caption, one ChatGPT image file and an explicit future local time. Reuse request_key when retrying this same intended post."),
    "update_post": (UpdatePostInput, PostResponse, "Modify an eligible saved draft's caption or time. Scheduled, in-progress and uncertain-outcome posts cannot be edited."),
    "schedule_post": (SchedulePostInput, ScheduleResponse, "Schedule an existing post. Defaults to dry_run. For facebook_schedule, first show the exact caption, image, Page and local time and obtain the user's approval. Both backend switches must be enabled. Never retry an uncertain write; retrieve the existing post instead."),
    "create_and_schedule_post": (CreateAndScheduleInput, PostAndSchedule, "Create and schedule exactly one intended post using a stable request_key. Defaults to dry_run. Obtain approval of the exact content, Page and time before facebook_schedule. Replays reuse the saved outcome and never initiate a second write."),
}
SCHEMES = [{"type": "oauth2", "scopes": ["email"]}]
logger = logging.getLogger(__name__)


def tool_descriptors() -> list[Tool]:
    result = []
    for name, (input_model, output_model, description) in CONTRACTS.items():
        read_only = name in {"get_system_status", "test_facebook_connection", "list_posts", "get_post"}
        publishing = name in {"schedule_post", "create_and_schedule_post"}
        meta: dict[str, Any] = {"securitySchemes": SCHEMES}
        if name in {"create_post", "create_and_schedule_post"}:
            meta["openai/fileParams"] = ["image"]
        result.append(Tool(
            name=name, title=name.replace("_", " ").title(), description=description,
            inputSchema=input_model.model_json_schema(),
            outputSchema=ToolOutput[output_model].model_json_schema(),
            annotations=ToolAnnotations(
                readOnlyHint=read_only, destructiveHint=publishing or name == "update_post",
                openWorldHint=publishing,
                idempotentHint=read_only or name in {"create_post", "create_and_schedule_post"},
            ),
            # The Python SDK's standard Tool type carries host extensions in _meta.
            _meta=meta,
        ))
    return result


def error_output(error: AppError, post_id: str | None = None) -> ToolOutput:
    return ToolOutput(ok=False, error=ToolError(code=error.code, message=error.message, post_id=post_id))


def mcp_result(output: ToolOutput) -> CallToolResult:
    data = output.model_dump(mode="json")
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))],
        structuredContent=data, isError=not output.ok,
    )


class SchedulerTools:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.media = MediaService(settings)
        self.downloader = ChatGPTFileDownloader(settings)
        self.connection = FacebookConnectionService(settings, FacebookClient(settings))

    async def call(self, name: str, raw: dict[str, Any]) -> CallToolResult:
        actor = get_access_token()
        if actor is None or not actor.subject:
            output = error_output(AppError(code="AUTH_REQUIRED", message="Connect the authorized operator account.", status_code=401))
            result = mcp_result(output)
            result.meta = {"mcp/www_authenticate": f'Bearer resource_metadata="{self.settings.mcp_resource_url.rsplit("/", 1)[0]}/.well-known/oauth-protected-resource/mcp", scope="email"'}
            return result
        try:
            if name not in CONTRACTS:
                raise AppError(code="UNKNOWN_TOOL", message="This tool is not available.", status_code=404)
            args = CONTRACTS[name][0].model_validate(raw)
            with get_session_factory(self.settings.require_database_url())() as session:
                if isinstance(args, CreatePostInput):
                    output = await self._create(session, actor.subject, name, args)
                else:
                    data = await self._execute(session, name, args)
                    output = ToolOutput[CONTRACTS[name][1]](ok=True, data=data)
                return mcp_result(output)
        except ValidationError:
            return mcp_result(error_output(AppError(code="VALIDATION_ERROR", message="The tool input contains invalid or missing fields.", status_code=422)))
        except AppError as error:
            post_id = raw.get("post_id") if isinstance(raw.get("post_id"), str) else None
            return mcp_result(error_output(error, post_id))
        except Exception:
            # Neither SDK exception serialization nor logs may leak signed input URLs.
            logger.error("MCP tool failed safely", extra={"event": "mcp_tool_failed"})
            return mcp_result(error_output(AppError(code="INTERNAL_ERROR", message="The tool could not complete. Inspect the existing post before retrying.", status_code=500)))

    async def _execute(self, session: Session, name: str, args: Any) -> BaseModel:
        posts = PostService(session, self.settings)
        if name == "get_system_status":
            return system_status(self.settings)
        if name == "test_facebook_connection":
            return await self.connection.test_connection()
        if name == "get_post":
            return posts.get_post(args.post_id)
        if name == "list_posts":
            page = posts.list_posts(status=args.status, limit=args.limit, offset=args.offset)
            summaries = [PostSummary(
                **{k: v for k, v in post.model_dump().items() if k in PostSummary.model_fields},
                caption_preview=post.caption[:280],
            ) for post in page.items]
            next_offset = args.offset + len(page.items)
            return PostPage(items=summaries, total=page.total, next_offset=next_offset if next_offset < page.total else None)
        if name == "update_post":
            return posts.update_post(args.post_id, PostUpdateRequest(**args.model_dump(exclude={"post_id"})))
        if name == "schedule_post":
            return await SchedulingService(session, self.settings, media_service=self.media).schedule_post(args.post_id, requested_mode=args.mode)
        raise AppError(code="UNKNOWN_TOOL", message="This tool is not available.", status_code=404)

    def _reserve(self, session: Session, actor: str, name: str, args: CreatePostInput) -> tuple[McpOperation, bool]:
        payload = args.model_dump(exclude={"request_key", "image"})
        payload["file_id"] = args.image.file_id
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        operation = McpOperation(operator_id=actor, tool=name, request_key=args.request_key, fingerprint=fingerprint)
        session.add(operation)
        try:
            session.commit()
            return operation, True
        except IntegrityError:
            session.rollback()
            previous = session.scalar(select(McpOperation).where(
                McpOperation.operator_id == actor, McpOperation.tool == name,
                McpOperation.request_key == args.request_key,
            ))
            if previous is None:
                raise
            if previous.fingerprint != fingerprint:
                raise AppError(code="REQUEST_KEY_CONFLICT", message="This request key belongs to different content. Inspect the original post.", status_code=409)
            return previous, False

    async def _create(self, session: Session, actor: str, name: str, args: CreatePostInput) -> ToolOutput:
        operation, fresh = self._reserve(session, actor, name, args)
        if not fresh:
            if operation.response is not None:
                return ToolOutput[CONTRACTS[name][1]].model_validate(operation.response).model_copy(update={"replayed": True})
            return error_output(AppError(code="OPERATION_IN_PROGRESS", message="This request is already recorded and may be in progress or interrupted. Inspect its post; do not create another copy.", status_code=409), operation.post_id)

        upload = None
        try:
            if isinstance(args, CreateAndScheduleInput) and args.mode is SchedulingMode.FACEBOOK_SCHEDULE and not self.settings.publishing_enabled:
                raise AppError(code="PUBLISHING_DISABLED", message="Real scheduling requires both backend publishing switches.", status_code=503)
            upload = await self.downloader.download(args.image)
            # Keep upload, committed post association, scheduling and result recording together
            # through a normal client disconnect. A killed process leaves the key reserved.
            with anyio.CancelScope(shield=True):
                post = await create_post_from_upload(
                    session, self.settings, self.media, caption=args.caption,
                    scheduled_for_local=args.scheduled_for_local, timezone=args.timezone,
                    image=upload, before_commit=lambda post_id: setattr(operation, "post_id", post_id),
                )
                if isinstance(args, CreateAndScheduleInput):
                    schedule = await SchedulingService(session, self.settings, media_service=self.media).schedule_post(post.id, requested_mode=args.mode)
                    data = PostAndSchedule(post=PostService(session, self.settings).get_post(post.id), schedule=schedule)
                else:
                    data = post
                output = ToolOutput[CONTRACTS[name][1]](ok=True, data=data)
                self._complete(session, operation, output)
                return output
        except AppError as error:
            session.rollback()
            output = error_output(error, operation.post_id)
        except Exception:
            session.rollback()
            output = error_output(AppError(code="INTERNAL_ERROR", message="Creation did not complete. Inspect the recorded post before any retry.", status_code=500), operation.post_id)
        finally:
            if upload is not None:
                with anyio.CancelScope(shield=True):
                    await upload.close()
        self._complete(session, operation, output)
        return output

    @staticmethod
    def _complete(session: Session, operation: McpOperation, output: ToolOutput) -> None:
        operation.response = output.model_dump(mode="json")
        operation.completed_at = datetime.now(UTC)
        session.commit()
