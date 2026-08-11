# Facebook Page Operations Dashboard

A local-first web application for managing already-created Facebook Page content.

## What We Are Building First

The first version is a **GUI Facebook Page scheduler**.

A user supplies:

- a written caption
- one image
- a future publication date/time

The application validates the input, shows a preview, stores a local record, and — when real publishing is explicitly enabled — schedules the content to a Facebook Page using the official Meta Graph API.

The purpose of V1 is to prove that our system can reliably manage and schedule existing content. AI content creation is deliberately excluded.

## Product Direction

The intended progression is:

```text
V1  Scheduling existing content
    ↓
V2  Better content library / queue / calendar management
    ↓
V3  Content scoring
    ↓
V4  Analytics and performance dashboard
    ↓
V5  Comment management
    ↓
V6  Content creation and research automation
```

The order may evolve, but content creation should remain later than the operations foundation.

## V1 User Flow

```text
Open web app
    ↓
Paste caption
    ↓
Upload one image
    ↓
Choose date and time
    ↓
Preview
    ↓
Save Draft or Schedule
    ↓
Backend validates request
    ↓
Dry run OR Meta Graph API
    ↓
Store status, response metadata, and errors
```

## V1 Screens

The first release needs only:

1. **Overview** — basic connection and post-status summary.
2. **New Post** — caption, image, date/time, preview, draft/schedule actions.
3. **Posts** — list of draft, scheduled, published/confirmed, cancelled, and failed records known to our application.
4. **Post Details** — content, image, timing, status, external ID, and error information.
5. **Settings / Connection** — non-secret connection status and safe configuration information.

A complex analytics dashboard is not part of V1.

## Technology

- React + TypeScript + Vite
- FastAPI
- SQLite
- SQLAlchemy
- Pydantic
- `httpx`
- Meta Graph API

## Safe Default

The application must start in dry-run mode:

```env
AUTOMATION_ENABLED=false
PUBLISH_MODE=dry_run
```

In dry run, users can exercise the complete UI and local workflow, but no Facebook write request is made.

## Repository Documentation

Read these before implementation:

- `AGENTS.md`
- `docs/MVP_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/SAFETY_RULES.md`

## Current Scope

V1 is single-user and local-first. It is intended to prove the scheduling core, not to ship a public SaaS product.

## Phase 2/3 Local Workflow

The repository now contains the complete local post-management and dry-run workflow:

- a FastAPI backend with safe environment settings, SQLite/SQLAlchemy initialization, structured logging, local-development CORS, and health/system-status APIs
- controlled JPEG/PNG storage with decoded-image, MIME, extension, filename, path, empty-file, and size validation
- timezone-explicit local input converted to aware UTC for persistence
- local post creation, listing, detail, editing, and controlled media APIs
- a dry-run scheduling service with persisted attempt history and backend duplicate-attempt protection
- a React + TypeScript + Vite dashboard with live forms, preview, posts, details, editing, dry-run results, and local operational counts
- backend tests that require neither Facebook credentials, internet access, nor a Meta developer account

A successful dry run leaves the post `ready`; it never uses the `scheduled` status reserved for future Meta acceptance. Every dry-run attempt records `external_request_made=false`, and no fake Facebook identifier is created. Facebook connection testing and real scheduling remain intentionally unimplemented.

## Local Setup

Prerequisites:

- Python 3.11 or newer
- Node.js 20.19 or newer

Optional local configuration can be created from the safe example:

```bash
cp .env.example .env
```

The defaults work without a `.env` file and keep automation disabled in dry-run mode.

### Backend

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend is available at `http://127.0.0.1:8000`. Its current endpoints are:

- `GET /api/health`
- `GET /api/system/status`
- `POST /api/posts`
- `GET /api/posts`
- `GET /api/posts/{id}`
- `PATCH /api/posts/{id}`
- `POST /api/posts/{id}/schedule`
- `GET /api/media/{generated_filename}`

Run backend tests from `backend/` with the virtual environment active:

```bash
pytest
```

### Frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. The frontend expects the backend at `http://127.0.0.1:8000` by default. A different backend URL may be supplied as the non-secret `VITE_API_BASE_URL` environment variable.

Build the frontend from `frontend/`:

```bash
npm run build
```

SQLite data is stored in `backend/data/app.db` by default. Validated images are stored under `backend/data/uploads/`. Both are intentionally ignored by Git except for the upload-directory placeholder.

## Phase 2/3 Project Structure

```text
backend/
├── app/
│   ├── api/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── config.py
│   ├── database.py
│   ├── logging_config.py
│   └── main.py
├── data/
├── tests/
└── pyproject.toml
frontend/
├── src/
│   ├── api/
│   ├── components/
│   ├── pages/
│   ├── state/
│   ├── types/
│   ├── utils/
│   └── types/
├── package.json
└── vite.config.ts
```
