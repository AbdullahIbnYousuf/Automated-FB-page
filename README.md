# Facebook Page Operations Dashboard

A single-operator web dashboard for managing already-created Facebook Page content. Phases 1–4 provide the hosted content workflow, dry-run scheduling, and a secure Page connection test. Phase 5 adds one guarded capability: scheduling an existing caption and one image to the configured Facebook Page through the official Meta Graph API.

The private **The Test Lab Operations** ChatGPT plugin exposes the same services through an OAuth-protected Streamable HTTP MCP endpoint on the existing Render backend. See [ChatGPT setup and acceptance](docs/CHATGPT_MCP.md) for deployment, consent, file transfer, replay protection, and the first explicitly approved live test. Code availability alone does not establish a connected plugin or successful live scheduling.

The separate private Sites client has a narrower [Facebook Scheduler Bridge contract and setup](docs/FACEBOOK_SCHEDULER_BRIDGE.md): `MCP_BRIDGE_CLIENT_ID` restricts its verified token to reads, draft creation and scheduling, with no protected REST access. Scheduling defaults to dry run. Explicit live scheduling additionally requires `MCP_BRIDGE_ALLOW_LIVE_SCHEDULING=true` and both existing publishing switches.

ChatGPT image delivery keeps the exact `MCP_FILE_ALLOWED_HOSTS` list. Optional
`MCP_FILE_ALLOWED_DOMAIN_SUFFIXES` defaults empty and supports only reviewed
`oaiusercontent.com` subdomains; Azure accounts remain individual exact entries.
See [the host policy and proposed production configuration](docs/CHATGPT_IMAGE_TRANSFER.md).

## Current architecture

```text
Browser / phone
    ↓
Cloudflare Pages — React + TypeScript + Vite
    ↓ Bearer token from Supabase Auth
Render Free Web Service — FastAPI
    ├── read-only Page identity GET
    └── guarded photo/video scheduling → Meta Graph API
    ↓
Supabase Free
├── PostgreSQL — posts and scheduling_attempts
├── private Storage — validated post images and videos
└── Auth — one email/password operator
```

Local React and FastAPI development use the same Supabase project. SQLite and local upload files are no longer runtime persistence; any old files under `backend/data/` are retained only as rollback/reference data.

## Product boundary

The operator supplies:

- a caption
- exactly one JPEG/PNG image or MP4 video (H.264, optional AAC, up to 20 MiB)
- a future date/time interpreted in `Asia/Dhaka`

The dashboard can save, list, view, edit, and schedule the post. In safe defaults, scheduling is simulated: the post remains `ready`, `external_request_made=false`, and no Facebook identifier is created. When both backend write switches are intentionally enabled, the same endpoint uploads the validated private image bytes and schedules one Page photo. Only Meta-confirmed acceptance produces `scheduled` and a stored Facebook reference.

Out of scope: immediate publishing, remote edit/cancellation/deletion, automatic write retries, analytics, comments, scoring, AI generation, multiple users, public signup, teams, billing, background workers, and paid infrastructure.

## Safety defaults

```env
AUTOMATION_ENABLED=false
PUBLISH_MODE=dry_run
APP_TIMEZONE=Asia/Dhaka
AUTH_REQUIRED=true
```

Real Facebook scheduling remains blocked unless both `AUTOMATION_ENABLED=true` and `PUBLISH_MODE=facebook_schedule`. Video additionally requires `VIDEO_FACEBOOK_SCHEDULING_ENABLED=true` (default: false) and separate confirmation of the saved draft, caption, Page and time. Credentials alone never enable writes. Mixed configuration fails closed, and write requests are never automatically retried.

## Local setup

Prerequisites:

- Python 3.11+
- Node.js 20.19+
- access to the configured Supabase project

Create backend configuration:

```bash
cp .env.example .env
```

Set `DATABASE_URL` to the Supabase shared session-pooler URL with TLS, then configure the Supabase URL, publishable key, secret key, Storage bucket, and authorized operator email. For a Facebook connection test, also configure the Graph API version, Page ID, and Page access token. Never commit `.env`.

Install and run the backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Create browser-safe frontend configuration:

```bash
cp frontend/.env.example frontend/.env.local
```

Only set `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_PUBLISHABLE_KEY` in that file. Then run:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173` and sign in with the authorized operator account.

## Tests and build

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app tests

cd ../frontend
npm test
npm run build
```

Backend tests use isolated SQLite databases, an in-memory fake Storage service, and mocked Meta transports. They do not require or mutate live Supabase resources and never create a real Facebook post.

## Supabase migrations

Reproducible SQL lives in `supabase/migrations/`. After linking the intended project:

```bash
supabase link --project-ref <project-ref>
supabase db push
supabase config push
```

The migration creates `posts`, `scheduling_attempts`, indexes, restrictive RLS posture, and the private `post-images` bucket with a 5 MiB JPEG/PNG limit. Public signup is disabled in `supabase/config.toml`.

## Deployment

- Frontend: [https://facebook-page-operations-dashboard.pages.dev](https://facebook-page-operations-dashboard.pages.dev)
- Backend: [https://facebook-page-operations-api.onrender.com](https://facebook-page-operations-api.onrender.com)
- Supabase: `Facebook Page Operations Dashboard` (`dqgaviukwfyaxqswraaf`), Singapore (`ap-southeast-1`)
- `render.yaml` defines exactly one Singapore `plan: free` Python web service with no disk or Render datastore.
- Build with the three browser-safe Vite variables and deploy `frontend/dist` using `npx wrangler pages deploy`.
- Routing: `frontend/public/_redirects` provides the SPA fallback for nested-route refreshes.
- CORS: production must set `FRONTEND_ORIGINS` to the exact Cloudflare Pages origin plus the two documented local development origins; wildcard CORS is not used.

The schema, private bucket, Render service, Pages site, and single-operator authentication are live.

Facebook secrets belong only on Render:

```env
FACEBOOK_GRAPH_API_VERSION=v26.0
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_REQUEST_TIMEOUT_SECONDS=10
```

Never add these values to Cloudflare Pages, Vite variables, Supabase rows, commits, screenshots, or chat. See [docs/META_SETUP.md](docs/META_SETUP.md) for the manual Meta-side setup.

## API

Public:

- `GET /api/health`
- `GET /.well-known/oauth-protected-resource/mcp` — public MCP OAuth configuration only

The frontend also provides public `/privacy` and `/data-deletion` pages. `/oauth/consent` preserves the existing operator login and verifies authorization before approval.

Requires a valid authorized Supabase Bearer token:

- `GET /api/system/status`
- `GET /api/facebook/status` — local safe status; no Meta request
- `POST /api/facebook/test-connection` — explicit read-only Meta request
- `POST /api/posts`
- `POST /api/posts/video` — authenticated multipart MP4 draft upload
- `GET /api/posts`
- `GET /api/posts/{id}`
- `PATCH /api/posts/{id}`
- `POST /api/posts/{id}/schedule` — backend selects dry run or guarded Facebook scheduling
- `POST /api/posts/{id}/schedule-video` — explicitly schedules one reviewed saved video; never falls back to dry run
- `GET /api/media/{object_path}`

Private images and videos are proxied through the authenticated backend. Supabase secret keys, database credentials, and Facebook tokens never enter the frontend.

`/mcp` is protected by Supabase OAuth on every request. In addition to the existing image tools, `create_video_post` accepts a temporary ChatGPT file reference. MP4 handoff depends on the client; if unavailable, use the dashboard and pass the draft ID to the scheduler. MCP scheduling defaults to `dry_run`; its real video action requires `confirm_video=true` after explicit approval. Dashboard video dry run is always available, and the existing photo action is unchanged.

When the separate video switch is intentionally enabled, open the saved video
draft in **Posts**, save any edits, then select **Review Facebook Video Schedule**.
Verify the playback preview, caption, configured Page ID and future Dhaka time
before clicking **Schedule Video on Facebook**. The backend rejects changed
drafts or Page IDs, stores the returned video ID, and never blindly retries.
The dashboard keeps the application's conservative 30-day ceiling for videos
as well as photos. A real Meta video test requires separate approval and must
be confirmed in the Page's scheduled-post interface; local mocks do not prove it.

For the first hosted video trial, verify that Supabase and Render are healthy,
apply the private video migration, and deploy the backend and dashboard. In
**New Post**, choose **Video**, attach a short MP4 (preferably under 6 MB for the
first trial), add a caption and future Dhaka time, and select **Save Draft**.
Reopen it, verify playback, then run a dry-run schedule. Leave publishing off.
The existing `post-images` limit stays 5 MiB. The new private `post-videos` bucket
must allow `video/mp4` up to the selected video cap; the hosted global limit was
last verified at 50 MiB. Do not use a broad hosted configuration push just to
change the local Storage limit. Before advertising the full 20 MiB cap, verify
the authenticated deployment can reliably transfer a boundary-sized clip.

The connection test targets Graph API `v26.0` and sends exactly `GET /v26.0/{page-id}?fields=id,name` with the Page token in the HTTPS `Authorization` header.

Real mode sends one multipart `POST /v26.0/{page-id}/photos` containing `source`, `caption`, `published=false`, `scheduled_publish_time` as whole Unix seconds, and `unpublished_content_type=SCHEDULED`. The documented scheduling window is at least 10 minutes and no more than 30 days from the request; the backend adds a small minimum-boundary buffer. The token remains only in the authorization header. A transport timeout/reset becomes `FACEBOOK_OUTCOME_UNKNOWN` and the record cannot be resubmitted automatically or manually through the current UI.

The current hosted Storage service requires the backend-only legacy `service_role` JWT for its `Authorization` header. It is stored under the generic `SUPABASE_SECRET_KEY` server variable because the newer opaque scoped secret is not accepted by this Storage endpoint version. The legacy key is never exposed to Vite or committed.

## Foundational documents

- `AGENTS.md`
- `docs/MVP_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/SAFETY_RULES.md`
