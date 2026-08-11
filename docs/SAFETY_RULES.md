# Safety, Security, and Publishing Rules

These rules override convenience. When uncertain, fail closed and do not publish.

## 1. Safe Default

The application must default to:

```env
AUTOMATION_ENABLED=false
PUBLISH_MODE=dry_run
APP_TIMEZONE=Asia/Dhaka
```

A real Facebook scheduling write is permitted only when:

```env
AUTOMATION_ENABLED=true
PUBLISH_MODE=facebook_schedule
```

The backend — not the frontend — enforces this rule.

## 2. Secrets

Secrets include at minimum:

- Facebook Page access token
- future API keys
- future webhook secrets

Rules:

- store secrets in environment variables for V1
- `.env` must be gitignored
- `.env.example` contains names and safe defaults only
- never expose the Page access token to the browser
- never put it in frontend environment variables
- never print it in logs
- never include it in exception text returned to the client
- never commit it to Git history

If a token is accidentally committed or exposed, treat it as compromised and rotate/revoke it.

## 3. Official API Only

Facebook publishing must use the official Meta Graph API.

Forbidden:

- Selenium Facebook automation
- Puppeteer Facebook automation
- Playwright Facebook automation
- browser-cookie automation
- password automation
- scripting clicks in facebook.com
- scraping Facebook as a substitute for the API

This project is a Page management application, not a browser bot.

## 4. Page Scope

V1 operates on one configured Facebook Page.

It must not:

- publish to the user's personal profile
- discover and publish to arbitrary Pages
- support other users' Pages
- mass-post across Pages

Those would require a separate product/security review.

## 5. Permission Minimization

Request/use only permissions required by the implemented capability.

For Page post management, `pages_manage_posts` is a core permission. Additional Page permissions may be necessary for Page discovery, connection checks, reads, or future functionality; only add them when the feature requires them and document why.

Do not pre-request analytics, comment, messaging, or unrelated permissions for V1.

## 6. External Write Guard

Before every real Facebook scheduling write, the backend must verify:

- automation is enabled
- publish mode is `facebook_schedule`
- Page ID exists
- Page token exists
- post exists
- post is in a valid state
- caption is valid
- image is valid and readable
- schedule time is valid
- request is not an obvious duplicate/repeated click

Any failure means no external write.

## 7. Retry Safety

Do not automatically retry a write request when the outcome is ambiguous.

Example: if the network connection drops after sending a scheduling request, it may be unclear whether Meta accepted it. Blind retrying can create duplicate scheduled posts.

For V1:

- safe read/connection checks may use limited retry logic
- real write retries should be conservative
- ambiguous write failures should be surfaced for operator review
- persist attempt metadata before manual retry

## 8. Time Safety

Scheduling errors can create unwanted immediate/incorrect publication times.

Rules:

- show the timezone in the UI
- parse local time on the backend using an IANA timezone
- convert to UTC internally
- reject past times
- enforce Meta's currently documented scheduling window before real requests
- never silently “fix” an invalid time to a different time

## 9. File Upload Safety

For image uploads:

- allow only explicitly supported image types
- check MIME type and extension
- enforce a configurable maximum size
- generate the stored filename server-side
- prevent `../` path traversal
- never execute uploaded files
- do not trust client filenames
- do not overwrite an existing file accidentally

## 10. Logging and Errors

Logs should help debugging without exposing secrets.

May log:

- internal post ID
- action
- state transition
- HTTP status
- Meta error code/type when safe
- request duration

Must not log:

- access tokens
- Authorization headers
- full external request bodies if they contain secrets
- `.env` contents
- browser/session credentials

Errors returned to the GUI should be actionable but sanitized.

## 11. Database Safety

V1 SQLite data is local application data.

- do not store Facebook access token in the `posts` table
- use database transactions around important state changes
- avoid marking a post `scheduled` before Meta confirms success
- preserve failure information rather than silently resetting state

## 12. Dry-Run Guarantee

Dry run must be testable.

Automated tests should verify that when dry run is active, the real Facebook client write method is not called.

A visible `DRY RUN` indicator should exist in the GUI when the app cannot publish.

## 13. Dependency and TLS Rules

- do not disable TLS certificate verification
- prefer maintained libraries
- keep dependency count low
- do not add a dependency solely to avoid writing a few lines of ordinary code
- pin/lock dependencies in the normal ecosystem-appropriate way once implementation begins

## 14. Future Features

Analytics, comments, scoring, AI generation, and additional platforms require new threat/safety reviews. Do not assume V1's permissions or data model are sufficient for them.
