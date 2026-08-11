# Architecture — Scheduler V1

## 1. Architectural goal

Keep the scheduling core small, explicit, testable, and safe while making the current post-management and dry-run dashboard available to one operator from a browser or phone.

```text
┌───────────────────────────────────────┐
│ Cloudflare Pages                     │
│ React + TypeScript + Vite            │
│ Supabase Auth session; no secrets    │
└──────────────────┬────────────────────┘
                   │ HTTPS + Bearer token
                   ▼
┌───────────────────────────────────────┐
│ Render Free Web Service              │
│ FastAPI validation + orchestration   │
└──────────────┬──────────────┬─────────┘
               │              │
               ▼              ▼
┌─────────────────────┐  ┌──────────────────────┐
│ Supabase PostgreSQL │  │ Supabase Storage     │
│ posts + attempts    │  │ private post-images  │
└─────────────────────┘  └──────────────────────┘
               │
               ▼ future only
┌───────────────────────────────────────┐
│ Facebook integration service         │
│ official Meta Graph API only         │
└───────────────────────────────────────┘
```

Local React and FastAPI processes connect to the same Supabase services through environment variables. SQLite and local uploaded files are retained only as rollback/reference data, not a parallel runtime architecture.

## 2. Deployment topology

- Frontend: Cloudflare Pages default HTTPS domain, static Vite output.
- Backend: one Render Free Python web service in Singapore, no persistent disk and no Render database/worker.
- Persistence: one Supabase Free PostgreSQL project in Singapore.
- Images: one private Supabase Storage bucket named `post-images`.
- Authentication: Supabase email/password Auth with public signup disabled and one backend-allowlisted operator email.
- Domain: platform default domains only; no purchased/custom domain.

All infrastructure must remain on free plans. Any action that requires billing, a paid add-on, persistent Render disk, or a paid instance is prohibited.

## 3. Frontend responsibilities

The frontend owns:

- email/password login, persisted session, refresh handling, and logout
- forms, file selection, and local image preview
- post/list/detail presentation
- loading, success, failure, and dry-run states
- attaching the current Supabase access token to backend calls
- loading private image bytes through the authenticated backend proxy

Allowed Vite variables are only:

```env
VITE_API_BASE_URL=
VITE_SUPABASE_URL=
VITE_SUPABASE_PUBLISHABLE_KEY=
```

The frontend must never receive the Supabase secret key, database URL/password, Facebook access token, or Render secrets. It must not call Meta or write directly to PostgreSQL/Storage.

## 4. Backend responsibilities

The backend owns:

- Supabase access-token verification and the single-operator email allowlist
- authoritative validation, timezone conversion, and state transitions
- SQLAlchemy persistence to Supabase PostgreSQL
- image validation and private Storage operations using a server-side key
- authenticated media proxying
- dry-run scheduling and immutable attempt history
- safe configuration/status responses and structured logs
- future Facebook integration behind a dedicated service boundary

`GET /api/health` is public. System status, posts, scheduling, and media routes require an authenticated authorized operator.

## 5. Data model

### `posts`

```text
id                       text UUID primary key
caption                  text, required
image_object_path        stable private Storage path, unique
image_mime_type          image/jpeg or image/png
original_filename        display-only basename
status                   draft|ready|scheduling|scheduled|failed|cancelled
scheduled_for_utc        timestamptz
display_timezone         Asia/Dhaka initially
facebook_object_id       nullable
last_error_code          nullable
last_error_message       nullable, sanitized
last_attempted_at        timestamptz nullable
created_at               timestamptz
updated_at               timestamptz
```

### `scheduling_attempts`

```text
id
post_id                  foreign key; cascade on post deletion
mode                     dry_run
result                   in_progress|success|failed
safe_message
error_code               nullable
external_request_made    false for every current attempt
created_at
completed_at             nullable
```

The committed Supabase migration is authoritative. Application startup validates database connectivity; it does not mutate the hosted schema. Tests may call SQLAlchemy metadata creation only against isolated SQLite fixtures.

Tables have RLS enabled and direct Data API grants revoked for `anon` and `authenticated`. Browser clients cannot bypass the FastAPI business rules.

## 6. Authentication boundary

The React app uses the official Supabase JavaScript client for session persistence and refresh. FastAPI validates each Bearer token against Supabase Auth's `/auth/v1/user` endpoint using the publishable key, then compares the returned email to `OPERATOR_EMAIL`.

Rules:

- never trust browser-supplied user identifiers
- missing, invalid, expired, or wrong-operator tokens fail closed
- no public registration UI, roles, profiles, teams, or social login
- hosted startup fails if Auth/Storage configuration is incomplete or Auth is disabled
- a 401 clears the local browser session

## 7. Storage boundary

The backend validates the entire upload before Storage receives it:

- one JPEG/PNG only
- MIME, extension, and decoded content must agree
- non-empty and at most 5 MiB
- decoded dimensions below the configured pixel ceiling
- UUID object name under `posts/`
- no overwrite and no client-controlled path

Only the stable object path is stored in PostgreSQL. The bucket is private. The authenticated backend checks the database reference and proxies the bytes; it never returns or persists privileged keys or permanent/signed public URLs.

## 8. Scheduling service boundary

Conceptually:

```python
schedule_post(post_id) -> ScheduleResult
```

The service claims an eligible post atomically, writes an in-progress attempt, validates caption/time/image availability, invokes the dry-run adapter, then commits the outcome. Duplicate in-progress attempts are rejected.

Current dry-run invariants:

```text
post.status = ready
attempt.external_request_made = false
post.facebook_object_id = null
```

No Facebook client exists in the hosted migration phase.

## 9. Future Facebook boundary

Phase 4 may add configuration and a read-only Page connection test. Phase 5 may add one real scheduled image post only after current official Meta documentation is re-verified.

Any future write remains backend-only and requires both:

```env
AUTOMATION_ENABLED=true
PUBLISH_MODE=facebook_schedule
```

The official Meta Graph API is the only permitted integration. Browser automation, cookies, scraping, and password automation remain forbidden.

## 10. Time and error rules

- The UI explicitly displays `Asia/Dhaka`.
- The backend interprets naive form input in that IANA timezone.
- PostgreSQL stores aware UTC instants in `timestamptz`.
- Past, nonexistent, and ambiguous local times are rejected rather than corrected.
- API errors are structured and sanitized.
- Logs may include route, internal post ID, state, safe error code, and duration; never credentials, tokens, authorization headers, `.env`, or secret-bearing bodies.

## 11. Reproducibility

- `supabase/config.toml` holds non-secret Auth/Storage configuration.
- `supabase/migrations/` holds the PostgreSQL and private-bucket schema.
- `render.yaml` declares exactly one free backend service and secret variable names with `sync: false`.
- `frontend/public/_redirects` provides the Cloudflare Pages SPA fallback.
- No large CI/CD system is required for this prototype.
