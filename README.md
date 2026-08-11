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
