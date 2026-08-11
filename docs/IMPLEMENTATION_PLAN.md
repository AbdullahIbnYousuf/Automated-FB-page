# Implementation Plan — Scheduler V1

## Current status

- Phase 0: complete
- Phase 1: complete
- Phase 2: complete
- Phase 3: complete
- Hosted Migration + Deployment: complete; Supabase, Render, Cloudflare, and single-operator authentication are live
- Phase 4: implemented; hosted valid-credential verification awaits manual Meta Page token setup
- Phase 5 and later: not started

## Principle

Build vertically in small, testable phases. Do not build the entire roadmap in one Codex prompt.

Every phase should leave the repository runnable and understandable.

## Phase 0 — Documentation Alignment

Before code:

- Codex reads all foundational docs.
- Codex summarizes the project, V1 scope, architecture, safety constraints, and implementation order.
- Codex does not write code in this phase.

Exit condition: Codex's summary matches the documented V1.

## Phase 1 — Application Skeleton

Goal: establish the React/FastAPI project with no Facebook logic.

Backend:

- FastAPI application
- configuration loader
- SQLite connection
- health endpoint
- CORS for local frontend development
- basic test setup

Frontend:

- React + TypeScript + Vite
- application shell/navigation
- routes/pages for Overview, New Post, Posts, Settings
- backend health check

Do not add Meta credentials or make external requests.

Exit condition:

- frontend starts
- backend starts
- frontend can display backend health
- backend tests run

## Phase 2 — Post Creation and Persistence

Goal: complete the content workflow. This phase originally used local persistence and was later migrated to Supabase by the hosted phase.

Implement:

- `Post` database model
- request/response schemas
- image upload validation/storage
- create draft endpoint
- list posts endpoint
- post detail endpoint
- basic update endpoint where needed
- New Post form
- image preview
- Posts list
- Post Details page

No scheduling call yet.

Exit condition:

A user can create a post with caption, one image, and intended schedule time, refresh/restart the app, and still see the saved record and image.

## Phase 3 — Dry-Run Scheduling

Goal: make the complete user workflow work safely without Facebook.

Implement:

- scheduling service
- scheduling state transitions
- backend schedule endpoint
- dry-run schedule adapter/result
- loading/success/failure UI
- mode banner indicating `DRY RUN`
- duplicate-click protection
- tests for valid and invalid transitions

Exit condition:

The GUI can “schedule” a stored post end-to-end while making zero Meta write requests.

## Hosted Migration + Deployment — Supabase, Render, and Cloudflare

Goal: securely expose the complete Phase 1–3 dashboard to one operator while remaining on free tiers and without advancing to Facebook Phase 4.

Implement:

- Supabase PostgreSQL as the authoritative application database
- committed migrations for `posts` and `scheduling_attempts`
- one private Supabase Storage bucket for validated post images
- Supabase email/password Auth with one authorized operator and public signup disabled
- Bearer authentication on every operational/system/media API except public health
- authenticated private-image proxying through FastAPI
- Cloudflare Pages deployment for the existing Vite UI
- one Render Free web service for FastAPI with no disk or Render datastore
- exact production/local CORS origins
- responsive operator login and existing phone-ready dashboard flow
- updated tests, environment examples, and deployment documentation

Safety requirements:

- keep `AUTOMATION_ENABLED=false` and `PUBLISH_MODE=dry_run`
- do not add or invoke a Facebook client
- do not expose database, Storage, Render, or Facebook secrets to Vite
- do not enable any paid resource or billing feature
- retain old physical SQLite/upload data as rollback evidence

Exit condition:

The Cloudflare Pages URL loads over HTTPS, authentication gates the dashboard, authenticated post/image/edit/dry-run flows persist through Supabase, sign-out removes access, and hosted evidence confirms `external_request_made=false` and `facebook_object_id=null`.

## Phase 4 — Facebook Configuration and Connection Test

Goal: prove that the backend can securely identify/access the configured Page.

Implement:

- environment configuration for:
  - Graph API version
  - Page ID
  - Page access token
- safe Facebook client
- `GET /api/facebook/status`
- `POST /api/facebook/test-connection`
- Settings/Connection screen
- meaningful auth/permission/config errors
- mocked client tests

Implementation notes:

- Graph API version verified against current official Meta documentation: `v26.0`
- connection request: read-only Page `id,name` lookup with a Page access token
- token transport: HTTPS `Authorization` header, never the URL
- safe last-check state is process-local and resets to `not_verified` after backend restart
- publishing capability remains explicitly unverified

Important:

- never send token to frontend
- never log token
- no scheduling request in this phase

Exit condition:

The GUI can say whether the configured Facebook Page connection is usable without exposing credentials.

## Phase 5 — Real Scheduled Image Post

Goal: achieve the core MVP milestone.

Implement the current official Meta Graph API flow for scheduling one Page image post with caption and future time.

Requirements:

- validate Meta scheduling window before request
- use the configured Graph API version
- use the Page access token backend-only
- send only the required parameters
- persist returned Facebook identifier
- map known Meta errors to safe application errors
- record scheduling attempt
- transition to `scheduled` only after a successful Meta response
- transition to `failed` on a confirmed failure
- do not blindly retry ambiguous writes

Real scheduling must be blocked unless:

```env
AUTOMATION_ENABLED=true
PUBLISH_MODE=facebook_schedule
```

Exit condition:

A manually prepared caption + image can be scheduled from our GUI to the configured Facebook Page and the returned identifier is stored locally.

## Phase 6 — MVP Hardening

Goal: make V1 reliable enough for repeated personal use.

Implement/review:

- input edge cases
- timezone tests
- file safety
- safe error presentation
- failed-post retry rules
- empty/loading states
- responsive basic layout
- database migration/init strategy
- startup instructions
- `.env.example`
- `.gitignore`
- secret/log audit
- tests of failure paths

Do not add future product features during hardening.

Exit condition: all MVP acceptance criteria in `MVP_SPEC.md` pass.

## Phase 7 — Manual Acceptance Test

Run a short acceptance checklist:

1. Start with empty database.
2. Create draft.
3. Refresh and verify persistence.
4. Restart backend and verify persistence.
5. Dry-run schedule a post.
6. Verify no Meta write happened.
7. Test invalid schedule time.
8. Test invalid image.
9. Test connection with missing configuration.
10. Test valid Page connection.
11. Enable real scheduling intentionally.
12. Schedule one test image post.
13. Verify Facebook identifier is stored.
14. Confirm expected scheduled content in Facebook's Page management interface.
15. Disable real scheduling again after the test if desired.

## What Comes After V1

Do not implement these until V1 is accepted.

Possible next work:

- better content queue/calendar
- edit/cancel synchronization
- post publication-status reconciliation
- content scoring
- analytics collection/dashboard
- comments inbox/management
- AI-assisted replies with human approval
- finally, research and content generation

## Codex Task Pattern

For each phase, use a prompt with this structure:

```text
Read AGENTS.md and all foundational docs first.

Implement Phase N only.
Do not implement later phases.

Before editing:
- summarize the phase goal
- list files you expect to create or modify
- state any important assumptions

Then implement the phase.

After implementation:
- run relevant tests
- summarize changes
- give exact commands to run the app/tests
- list remaining limitations

Keep the default safe and dry-run.
```
