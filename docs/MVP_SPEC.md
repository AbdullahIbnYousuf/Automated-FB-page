# MVP Specification — GUI Facebook Page Scheduler

## 1. Purpose

The MVP proves one capability:

> Given already-created Facebook content, can our application reliably and safely schedule it to a Facebook Page from our own GUI?

The user creates the content outside this application. V1 manages it.

## 2. Primary User Story

As the operator of a Facebook Page, I want to paste a caption, upload an image, choose a future date/time, preview the post, and schedule it from one dashboard so I do not need to manually create the scheduled post inside Facebook.

## 3. V1 Inputs

A schedulable post contains:

- `caption`: required text
- `image`: exactly one supported image file
- `scheduled_for`: required future local date/time
- `timezone`: application timezone; default `Asia/Dhaka`

V1 does not support multiple images, video, Reels, Stories, links as a distinct post type, or platform-specific variants.

## 4. V1 Outputs

For every post attempt, the system stores a persistent record containing at minimum:

- internal post ID
- caption
- stable private Storage object path
- created timestamp
- scheduled timestamp in UTC
- display timezone
- status
- Meta/Facebook object or post ID when available
- last error code/message when failed
- last scheduling attempt timestamp

The user sees a clear success or failure result in the GUI.

## 5. Post Status Model

Use an explicit state model. Minimum statuses:

- `draft` — saved by the application, not submitted to Meta
- `ready` — application-validated and ready to schedule
- `scheduling` — a real scheduling request is in progress
- `scheduled` — Meta accepted the scheduled content and returned an identifier
- `failed` — scheduling attempt failed
- `cancelled` — locally marked cancelled; remote cancellation behavior is a later capability unless implemented safely in V1

Do not claim `published` merely because the scheduled time has passed. A `published`/confirmed state should only be added once the application implements a reliable way to verify it through Meta.

## 6. Required Screens

### 6.1 Overview

Purpose: answer “is the system healthy and what is waiting?”

Show:

- current mode: Dry Run / Facebook Scheduling
- Facebook connection status: Connected / Not configured / Error
- number of drafts
- number of scheduled posts
- number of failed posts
- upcoming scheduled posts (small list)

No advanced charts in V1.

### 6.2 New Post

Required controls:

- caption textarea
- image file picker
- image preview
- date picker
- time picker
- displayed timezone
- post preview card
- `Save Draft` action
- `Schedule` action

Expected behavior:

- form validates before submission
- scheduling time is converted deterministically to UTC on the backend
- the UI clearly distinguishes dry-run from real scheduling
- while a request is in progress, repeated clicks cannot create duplicate submissions

### 6.3 Posts

Show posts known to our PostgreSQL database with:

- thumbnail
- short caption preview
- scheduled time
- status
- created time

Provide basic filters by status if inexpensive to implement.

### 6.4 Post Details

Show:

- full caption
- image
- local schedule time and timezone
- current status
- internal ID
- Meta/Facebook identifier when available
- created/updated times
- safe error information

V1 may include retry for a `failed` post only if duplicate-scheduling protection is implemented.

### 6.5 Settings / Connection

Show only safe, non-secret information:

- configured Page ID (masking is optional)
- Graph API version
- whether a Page token is configured
- connection test result
- current automation mode
- application timezone

Never show the full access token in the GUI.

## 7. Dry-Run Behavior

Dry run is a first-class feature, not a temporary hack.

When:

```env
AUTOMATION_ENABLED=false
```

or:

```env
PUBLISH_MODE=dry_run
```

`Schedule` must:

1. validate the content
2. store/update the persistent post
3. create a simulated scheduling result
4. make **no write request** to Meta
5. clearly label the record as dry-run/simulated in logs or metadata

Dry-run behavior should use the same validation and application flow as real scheduling wherever possible.

## 8. Real Scheduling Behavior

A real scheduling operation is allowed only when:

```env
AUTOMATION_ENABLED=true
PUBLISH_MODE=facebook_schedule
```

The backend must:

1. validate the local post
2. verify required Facebook configuration exists
3. validate the scheduled time against Meta's supported scheduling window
4. upload/create the scheduled Page photo post through the official Graph API flow
5. persist the returned identifier
6. transition the local status to `scheduled`
7. on failure, persist a safe error and transition to `failed`

Meta's current Graph API documentation supports Page scheduled posts with `scheduled_publish_time`; Page photo scheduling requires the relevant unpublished/scheduling parameters. Implementation must follow the current official Meta documentation at coding time rather than relying on guessed request shapes.

## 9. Validation Requirements

### Caption

- required for V1
- trim surrounding whitespace
- reject an empty result
- do not invent an arbitrary low character limit; surface Meta errors if a platform limit is reached, and add a validated limit only from official documentation

### Image

- exactly one image in V1
- validate MIME type and extension
- accept a deliberately small set initially, such as JPEG and PNG
- set a configurable file-size ceiling
- generate a unique stored filename
- never trust the original client filename as a filesystem path

### Schedule Time

- required
- must be in the future
- interpret user input using the configured application timezone
- convert to UTC internally
- before a real Meta request, validate against Meta's current allowed scheduling window

## 10. Facebook Requirements

The application targets a **Facebook Page**, not a personal profile.

Use the official Meta Pages/Graph API only.

Expected Page permissions/capabilities must be documented during the integration phase. `pages_manage_posts` is central to managing Page posts; additional permissions may be needed for discovering/reading the Page or later features.

Tokens stay backend-only.

## 11. Error Experience

Errors should be understandable without exposing secrets.

Good UI message:

> Facebook rejected the scheduling request. Check the Page connection and schedule time, then retry.

Developer details may be stored safely in backend logs, including Meta error type/code where useful, but never tokens.

The GUI must not show a generic success if Meta returned an error.

## 12. Duplicate Protection

At minimum:

- disable duplicate UI submissions while the first request is pending
- do not blindly retry write requests on network ambiguity
- store an attempt record/result before allowing manual retry

A later version may implement stronger idempotency semantics.

## 13. V1 Non-Goals

Explicitly excluded:

- AI generation or rewriting
- content scoring
- analytics
- comments
- engagement automation
- multi-platform support
- calendar drag-and-drop
- bulk CSV upload
- multiple Pages
- multiple images
- video/Reels
- public registration or multiple users
- roles/permissions
- SaaS billing
- paid infrastructure or custom domains

## 14. Acceptance Criteria

V1 is complete when all of the following are true:

1. The application starts locally with one documented command for frontend and backend (or a simple dev script).
2. A user can create a draft with caption, image, and schedule time in the GUI.
3. The image remains available after page refresh.
4. The draft remains available after application restart.
5. The user can see saved posts and post details.
6. Dry-run scheduling performs no Meta write request and produces an obvious simulated result.
7. The app can test Facebook Page connectivity without exposing the token.
8. With real mode intentionally enabled and valid credentials, one caption + image post can be scheduled successfully to the configured Facebook Page.
9. The returned Facebook identifier is stored.
10. A failed Meta request produces a `failed` local state and useful safe error.
11. Secrets are not committed, returned to the browser, or written to normal logs.
12. Core backend scheduling/state-transition behavior has automated tests.

## 15. Hosted single-operator boundary

The current operational deployment adds infrastructure without expanding the Facebook feature scope:

- React/Vite on Cloudflare Pages
- FastAPI on one Render Free web service
- Supabase PostgreSQL, private Storage, and email/password Auth
- exactly one backend-allowlisted operator
- no public signup UI, profiles, roles, teams, or SaaS behavior
- public health only; all dashboard data and images require authentication

This hosted migration does not implement Phase 4 connection testing or Phase 5 Facebook scheduling. Dry-run semantics and the two-switch future publishing guard remain unchanged.
