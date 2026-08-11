# Architecture — Scheduler V1

## 1. Architectural Goal

V1 should be small enough to understand completely but structured enough to support later content scoring, analytics, comments, and content creation without rewriting the scheduling core.

The architecture is deliberately split into UI, application API, persistence, and Facebook integration.

```text
┌───────────────────────────────┐
│ React + TypeScript Frontend   │
│ GUI only; no Meta secrets     │
└───────────────┬───────────────┘
                │ HTTP / JSON + multipart upload
                ▼
┌───────────────────────────────┐
│ FastAPI Backend               │
│ validation + orchestration    │
└───────┬───────────┬───────────┘
        │           │
        │           └──────────────────┐
        ▼                              ▼
┌───────────────┐              ┌──────────────────┐
│ SQLite        │              │ Local Media      │
│ post records  │              │ uploaded images  │
└───────────────┘              └──────────────────┘
        │
        ▼
┌───────────────────────────────┐
│ Facebook Integration Service  │
│ official Meta Graph API only  │
└───────────────────────────────┘
```

## 2. Recommended Repository Structure

```text
/
├── AGENTS.md
├── README.md
├── .env.example
├── .gitignore
├── docs/
│   ├── MVP_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── SAFETY_RULES.md
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   └── post.py
│   │   ├── schemas/
│   │   │   └── post.py
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── posts.py
│   │   │   └── facebook.py
│   │   ├── services/
│   │   │   ├── post_service.py
│   │   │   └── scheduling_service.py
│   │   └── integrations/
│   │       └── facebook/
│   │           ├── client.py
│   │           ├── types.py
│   │           └── errors.py
│   ├── tests/
│   └── data/
│       └── uploads/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── app/
        ├── components/
        ├── pages/
        ├── api/
        └── types/
```

This is a target structure, not a requirement to create every empty file immediately.

## 3. Backend Responsibilities

The backend owns:

- configuration
- input validation
- image storage
- timezone conversion
- post persistence
- state transitions
- dry-run simulation
- Facebook authentication/configuration checks
- Meta Graph API requests
- safe error mapping
- structured logs

The backend is the only layer allowed to read `FACEBOOK_PAGE_ACCESS_TOKEN`.

## 4. Frontend Responsibilities

The frontend owns:

- forms
- file selection and preview
- post preview
- list/detail presentation
- loading/success/failure states
- safe connection-status display

The frontend must not:

- contain or request the Facebook access token
- construct raw Meta Graph API calls
- determine whether a real write is safe
- treat a browser-only validation as authoritative

## 5. Data Model

### `posts`

Suggested V1 fields:

```text
id                       UUID or integer primary key
caption                  text, required
image_path               text, required
image_mime_type          text, required
status                   enum/string, required
scheduled_for_utc        datetime, nullable for draft
display_timezone         text, default Asia/Dhaka
facebook_object_id       text, nullable
is_dry_run               boolean, default true
last_error_code          text, nullable
last_error_message       text, nullable
scheduling_attempts      integer, default 0
created_at               datetime UTC
updated_at               datetime UTC
last_attempted_at        datetime UTC, nullable
```

Avoid storing the Page access token in the database in V1. Read it from environment configuration.

### Optional `activity_logs`

Only create this table if useful during implementation. Normal application logging plus fields on `posts` may be sufficient for V1.

If created:

```text
id
post_id nullable
action
result
safe_message
created_at
```

Do not store secret-bearing raw HTTP headers or full tokens.

## 6. API Shape

Exact route names may change slightly, but keep the API resource-oriented.

### Health

```text
GET /api/health
```

Returns application health and safe mode information.

### Posts

```text
GET    /api/posts
POST   /api/posts
GET    /api/posts/{id}
PATCH  /api/posts/{id}
POST   /api/posts/{id}/schedule
```

`POST /api/posts` should accept multipart/form-data in V1 so caption metadata and one image can be submitted together, or use a two-step upload flow if implementation quality clearly benefits. Keep it simple.

### Facebook Connection

```text
GET  /api/facebook/status
POST /api/facebook/test-connection
```

Responses must never contain the Page access token.

## 7. Scheduling Service Boundary

Create a scheduling service that orchestrates the flow without knowing HTTP/UI details.

Conceptually:

```python
schedule_post(post_id) -> ScheduleResult
```

It should:

1. load the post
2. check current state
3. validate required data
4. validate application mode
5. convert/check scheduling time
6. choose dry-run or Facebook implementation
7. persist the result/state
8. return a safe result

This service should be heavily testable with a fake Facebook client.

## 8. Facebook Client Boundary

Keep Meta-specific request details in one integration client.

Conceptual operations:

```python
class FacebookPageClient:
    async def test_connection(self) -> ConnectionResult: ...
    async def schedule_photo_post(
        self,
        *,
        caption: str,
        image_path: Path,
        scheduled_for_utc: datetime,
    ) -> FacebookScheduleResult: ...
```

The rest of the application should not know endpoint URLs, token query/body details, or Meta error payload shapes.

Use the official current Meta documentation when implementing the actual request. As of this document's creation, Meta Graph API documentation exposes Page feed and Page photos scheduling using `scheduled_publish_time`, and Page photo scheduling requires unpublished/scheduling parameters.

## 9. API Versioning

Do not scatter Graph API version strings through the code.

Use one configuration value:

```env
FACEBOOK_GRAPH_API_VERSION=v26.0
```

The current Meta documentation exposes Graph API v26.0. Pin the version deliberately and update it centrally after compatibility testing when Meta versions change.

## 10. Time Handling

The user initially operates in:

```text
Asia/Dhaka
```

Rules:

- frontend displays the configured timezone explicitly
- backend parses the user's intended local datetime in that timezone
- backend stores UTC
- backend sends the correct instant to Meta
- API returns ISO-8601 timestamps
- do not use naive datetimes in persistence/business logic

Meta's current Page feed documentation constrains scheduled Page posts to a future scheduling window. Validate this using the current official docs at implementation time and expose a friendly validation error instead of waiting for Meta to reject obvious invalid input.

## 11. Image Storage

V1 local storage is acceptable.

Rules:

- create a dedicated upload directory
- generate server-side filenames (UUID preferred)
- store original extension only after validating type
- validate MIME type and extension
- prevent path traversal
- do not serve arbitrary filesystem paths
- expose media through a controlled static route if required for the UI

Later versions can replace local storage with object storage behind a storage interface if necessary.

## 12. Error Model

Use application errors rather than leaking raw third-party payloads to the UI.

Example categories:

```text
VALIDATION_ERROR
CONFIGURATION_ERROR
FACEBOOK_AUTH_ERROR
FACEBOOK_PERMISSION_ERROR
FACEBOOK_SCHEDULE_ERROR
FACEBOOK_NETWORK_ERROR
DUPLICATE_ATTEMPT_RISK
INTERNAL_ERROR
```

Store the Meta error code/type where useful, but redact sensitive details.

## 13. Logging

Use structured backend logs with fields such as:

```text
action
post_id
status
provider=facebook
meta_error_code (when safe)
duration_ms
```

Never log:

- access tokens
- Authorization headers
- full `.env`
- browser credentials

## 14. Future Extensibility

Later capabilities should attach to the existing `posts` domain rather than replacing it:

- scoring adds score records/fields
- analytics attaches performance snapshots to published Facebook IDs
- comments attach conversation/comment records to Facebook post IDs
- content creation creates new drafts that enter the same scheduling workflow

That is why V1 must establish clean local post IDs, statuses, timestamps, and Facebook identifiers now.

## 15. Current Official Meta References

Use these as the primary references when implementing Phase 4 and Phase 5. Meta can change API versions, permissions, and request details, so implementation should be checked against the current version rather than copied from third-party tutorials.

- Facebook Pages API overview: `https://developers.facebook.com/documentation/pages-api`
- Pages API getting started: `https://developers.facebook.com/documentation/pages-api/getting-started`
- Pages API posts guide: `https://developers.facebook.com/documentation/pages-api/posts`
- Page Feed Graph API reference: `https://developers.facebook.com/docs/graph-api/reference/page/feed/`
- Page Photos Graph API reference: `https://developers.facebook.com/docs/graph-api/reference/page/photos/`
- Meta permissions reference: `https://developers.facebook.com/docs/permissions/`

At documentation time (2026-08-11), Meta's Graph API reference is on v26.0. The Page Feed reference documents `scheduled_publish_time` and a scheduling window beginning at least 10 minutes in the future and extending up to 75 days. The Page Photos reference documents that scheduled photo posts require the scheduling/unpublished parameters, including `published`, `scheduled_publish_time`, and `unpublished_content_type`. Re-verify these constraints immediately before implementing the real write request.
