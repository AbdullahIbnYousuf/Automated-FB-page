# AGENTS.md

## 1. Project Identity

This repository contains the first version of a larger Facebook Page operations and automation product.

The current product is a **GUI-based Facebook Page Scheduler**. A user provides already-created content — a caption, one image, and a future date/time — and the application safely schedules that content to a Facebook Page through the official Meta Graph API.

This repository is **not** an AI content-generation project yet. Content creation will be added much later. The near-term roadmap is to automate the management of existing content first: scheduling, content management, analytics, scoring, dashboard workflows, and comments.

## 2. Read Before Coding

Before implementing any task, read:

1. `README.md`
2. `docs/MVP_SPEC.md`
3. `docs/ARCHITECTURE.md`
4. `docs/IMPLEMENTATION_PLAN.md`
5. `docs/SAFETY_RULES.md`

Treat these files as the current source of truth. If two instructions conflict, use this priority order:

1. `docs/SAFETY_RULES.md`
2. `docs/MVP_SPEC.md`
3. `docs/ARCHITECTURE.md`
4. `docs/IMPLEMENTATION_PLAN.md`
5. `README.md`

Do not silently change a product or architecture decision. If a requested implementation conflicts with the docs, explain the conflict before changing code.

## 3. V1 Goal

V1 must let a user:

1. Open a web GUI.
2. Enter or paste a Facebook caption.
3. Upload one image.
4. Select a future publication date and time in the configured timezone.
5. Preview the content.
6. Save it as a draft or schedule it.
7. See whether scheduling succeeded or failed.
8. See the local record and Facebook object/post identifier when available.

The default mode is **dry run**. Nothing may be sent to Facebook until publishing is explicitly enabled.

## 4. Technology Decisions

Use the following stack unless the architecture document is intentionally updated:

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI
- Persistence: SQLite
- ORM/data layer: SQLAlchemy
- Validation: Pydantic
- HTTP client: `httpx`
- Image storage in V1: local filesystem, outside the frontend source tree
- Facebook integration: official Meta Graph API only
- Testing: `pytest` for backend; lightweight frontend tests where useful

Keep dependencies minimal. Do not introduce Docker, Redis, Celery, PostgreSQL, Next.js, a component framework, or cloud infrastructure unless a later requirement genuinely needs them.

## 5. Architecture Rules

- The browser/frontend must never receive the Facebook Page access token.
- All Meta Graph API calls must happen in the backend.
- Facebook-specific logic must stay behind a dedicated integration/service layer.
- UI components must not directly contain Meta API request logic.
- Scheduling domain logic must be testable without making a real Facebook request.
- External API calls must be mockable.
- The application must have a dry-run implementation path.
- Store times internally in UTC; display and accept user times using the configured timezone, initially `Asia/Dhaka`.
- Never rely on the browser's implicit timezone conversion without making the intended timezone explicit.

## 6. Safety Defaults

These are non-negotiable defaults:

```env
AUTOMATION_ENABLED=false
PUBLISH_MODE=dry_run
APP_TIMEZONE=Asia/Dhaka
```

A real scheduling request is allowed only when both of these are true:

```env
AUTOMATION_ENABLED=true
PUBLISH_MODE=facebook_schedule
```

Missing or invalid configuration must fail closed: do not publish.

## 7. V1 Non-Goals

Do not implement these unless the user explicitly changes the MVP:

- AI content generation
- Content research
- Content scoring
- Analytics
- Comment management
- Automatic replies
- Multi-platform publishing
- Instagram
- Threads
- TikTok
- YouTube
- X/Twitter
- Reels or video generation
- Multi-image posts/carousels
- Multi-user authentication
- Teams/workspaces
- Billing
- SaaS deployment
- Cloud object storage
- Mobile application
- Browser automation of Facebook

The database and code structure may leave room for later features, but do not build them now.

## 8. Coding Expectations

For each coding task:

1. State the plan briefly before editing.
2. Make the smallest coherent change that completes the requested phase.
3. Add tests for business logic and failure paths.
4. Run relevant tests and linters when available.
5. Summarize changed files and behavior.
6. State any assumptions or remaining limitations.

Prefer:

- small modules
- explicit types
- clear names
- dependency injection around external services
- meaningful error objects
- structured logs
- predictable state transitions

Avoid:

- giant files
- hidden global state
- hard-coded secrets
- hard-coded absolute paths
- broad exception swallowing
- fake success responses
- unnecessary abstractions
- premature generic platform frameworks in V1

## 9. Security Rules

Never:

- commit `.env`
- log full access tokens
- return access tokens through API responses
- put tokens in frontend code or localStorage
- disable TLS certificate verification
- automate Facebook with Selenium, Playwright, Puppeteer, or browser cookies
- silently retry an external write indefinitely

Playwright, if later used for rendering graphics, may only render local content. It is not needed in Scheduler V1.

## 10. Product Principle

The first milestone is not “maximum automation.” It is **reliable control of already-created content**.

Build a trustworthy scheduling core first. Later product versions can add content scoring, analytics, dashboard intelligence, comments, and finally content creation on top of that core.
