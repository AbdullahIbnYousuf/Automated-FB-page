# Facebook Page Operations Dashboard

A single-operator web dashboard for managing already-created Facebook Page content. Phases 1–3 provide draft creation, one-image upload, timezone-safe scheduling data, post management, and dry-run scheduling. Phase 4 adds a secure, read-only Facebook Page connection test through the official Meta Graph API.

## Current architecture

```text
Browser / phone
    ↓
Cloudflare Pages — React + TypeScript + Vite
    ↓ Bearer token from Supabase Auth
Render Free Web Service — FastAPI
    ├── read-only GET → Meta Graph API
    ↓
Supabase Free
├── PostgreSQL — posts and scheduling_attempts
├── private Storage — validated post images
└── Auth — one email/password operator
```

Local React and FastAPI development use the same Supabase project. SQLite and local upload files are no longer runtime persistence; any old files under `backend/data/` are retained only as rollback/reference data.

## Product boundary

The operator supplies:

- a caption
- exactly one JPEG or PNG image
- a future date/time interpreted in `Asia/Dhaka`

The dashboard can save, list, view, edit, and dry-run schedule the post. A successful dry run leaves the post `ready`, records `external_request_made=false`, and never creates a Facebook identifier. Settings can explicitly test the configured Facebook Page by reading only its `id` and `name`.

Out of scope for this phase: Facebook writes or real scheduling, analytics, comments, scoring, AI generation, multiple users, public signup, teams, billing, background workers, and paid infrastructure.

## Safety defaults

```env
AUTOMATION_ENABLED=false
PUBLISH_MODE=dry_run
APP_TIMEZONE=Asia/Dhaka
AUTH_REQUIRED=true
```

Real Facebook writes remain impossible because the Phase 4 client implements only one read-only Page identity request. Future real scheduling must also require both `AUTOMATION_ENABLED=true` and `PUBLISH_MODE=facebook_schedule`.

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
npm run build
```

Backend tests use isolated SQLite databases, an in-memory fake Storage service, and mocked Meta transports. They do not require or mutate live Supabase resources and never make a real Facebook request.

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

Requires a valid authorized Supabase Bearer token:

- `GET /api/system/status`
- `GET /api/facebook/status` — local safe status; no Meta request
- `POST /api/facebook/test-connection` — explicit read-only Meta request
- `POST /api/posts`
- `GET /api/posts`
- `GET /api/posts/{id}`
- `PATCH /api/posts/{id}`
- `POST /api/posts/{id}/schedule`
- `GET /api/media/{object_path}`

Private images are proxied through the authenticated backend. Supabase secret keys, database credentials, and Facebook tokens never enter the frontend.

The connection test targets Graph API `v26.0` and sends exactly `GET /v26.0/{page-id}?fields=id,name` with the Page token in the HTTPS `Authorization` header. Success proves Page identity/read access only. It does not prove `pages_manage_posts` or future publishing capability.

The current hosted Storage service requires the backend-only legacy `service_role` JWT for its `Authorization` header. It is stored under the generic `SUPABASE_SECRET_KEY` server variable because the newer opaque scoped secret is not accepted by this Storage endpoint version. The legacy key is never exposed to Vite or committed.

## Foundational documents

- `AGENTS.md`
- `docs/MVP_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/SAFETY_RULES.md`
