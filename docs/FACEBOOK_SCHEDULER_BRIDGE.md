# Private Facebook Scheduler Bridge support

This repository supplies the restricted MCP client boundary for the separate
private Sites bridge. The bridge calls the existing FastAPI `/mcp` endpoint;
posts, scheduling attempts, durable creation keys, private images, authentication
and Meta requests stay in the existing scheduler and Supabase project. No second
scheduling database, queue, image bucket or publishing implementation is needed.

## Client boundary

`MCP_BRIDGE_CLIENT_ID` is an optional, backend-only **public OAuth client ID**,
not a client secret. Use the exact ID of the dedicated Supabase OAuth client.
Leaving it unset or empty preserves existing clients but does not establish a
restricted bridge. The Sites bridge must refuse writes unless an authenticated
`get_system_status` response has `bridge_client_restricted=true`.

The backend matches that setting against the `client_id` from the verified MCP
access token, after signature, issuer, resource audience, expiry, scope and
operator checks. Headers, tool arguments and client names cannot choose the
identity. The flag is false for other clients, unset configuration and REST
status responses; it does not describe whether publishing is globally enabled.

| Restricted client's MCP action | Result |
| --- | --- |
| `get_system_status` | Allowed; returns the caller-specific restriction flag |
| `test_facebook_connection` | Allowed; existing read-only Page identity check |
| `list_posts`, `get_post` | Allowed |
| `create_post` | Allowed; saves one draft with a durable `request_key` |
| `schedule_post` with `mode=dry_run` or omitted mode | Allowed; simulation only |
| `schedule_post` with `mode=facebook_schedule` | `BRIDGE_ACTION_FORBIDDEN` |
| `update_post` | `BRIDGE_ACTION_FORBIDDEN` |
| `create_and_schedule_post` in any mode | `BRIDGE_ACTION_FORBIDDEN` |

Denied actions stop before draft reservation, download, editing or scheduling.
The restrictions still apply if the server's publishing gates are later enabled.
All protected REST routes, including private media, reject the restricted
client's token with `BRIDGE_REST_FORBIDDEN` after Supabase authenticates that exact
Bearer token. Public health and OAuth discovery remain public. The dashboard's
ordinary operator session and other authorized OAuth clients retain their
existing behavior and operator verification.

## Consent callback

The one additional callback is exactly:

```text
https://facebook-scheduler-bridge.sassypear13.chatgpt.site/oauth/callback
```

OAuth response query parameters such as `code`, `state` and `error` are allowed.
Alternate hosts, schemes, explicit ports, userinfo, fragments, path changes,
encoded paths, dot-segment normalization and backslash variants are rejected.
The existing ChatGPT HTTPS and numeric loopback restrictions remain in place.
The consent UI verifies the operator before fetching details and before either
decision. Only redirect values returned by Supabase are used, and Supabase must
validate the client's exact registered URI. A query parameter supplied to the
consent page is never used as a redirect destination.

## Image and replay protections

Both upload and pre-Meta private-object validation check type, size, dimensions,
container integrity and decoded pixels. PNG requires a complete terminal IEND
chunk, and every PNG animation frame is decoded within `MAX_IMAGE_PIXELS` as a
total decoded pixel budget. Corrupt compressed pixels and truncated endings
produce sanitized `INVALID_IMAGE` or `INVALID_STORED_IMAGE` errors before writes.

Creation retains the existing operator + tool + `request_key` reservation,
fingerprint, committed post association and recorded response. Reuse the same
key for the same intended creation. A refreshed signed URL is not a new payload;
changed caption/file ID/time conflicts. Pending reservations remain blocked for
inspection. Unknown Meta outcomes remain blocked from editing/resubmission;
there is no automatic takeover or retry. Signed file URLs are not persisted.

## Remaining setup, outside this repository-only change

1. Register a dedicated OAuth client in the existing Supabase project using the
   exact callback above. Complete PKCE, state, operator login and consent in the
   separate bridge; do not put operator or Meta credentials into the Site.
2. Set the returned public client ID as `MCP_BRIDGE_CLIENT_ID` on the existing
   backend. Deploy this backend and the existing consent frontend through a
   separately authorized rollout. Retain the safe settings below.
3. Verify real OAuth issuance and refresh, the authenticated restriction flag,
   Page identity read, actual image transfer, draft retrieval and a dry-run
   result with `external_request_made=false` and no Facebook ID. Local mocks do
   not establish hosted acceptance. No real publishing check is required for
   this bridge's allowed capabilities.

Exact environment-variable names:

| Purpose | Variables |
| --- | --- |
| New optional backend setting | `MCP_BRIDGE_CLIENT_ID` |
| Required safe settings | `AUTOMATION_ENABLED=false`, `PUBLISH_MODE=dry_run`, `AUTH_REQUIRED=true`, `APP_TIMEZONE=Asia/Dhaka` |
| Existing Supabase/operator settings, reused | `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_STORAGE_BUCKET`, `OPERATOR_EMAIL` |
| Existing MCP resource/file settings | `MCP_RESOURCE_URL`, `MCP_FILE_ALLOWED_HOSTS`, `MCP_FILE_TIMEOUT_SECONDS` |
| Existing image limits | `MAX_UPLOAD_BYTES`, `MAX_IMAGE_PIXELS` |
| Existing Meta configuration, reused | `FACEBOOK_GRAPH_API_VERSION`, `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`, `FACEBOOK_REQUEST_TIMEOUT_SECONDS` |
| Existing browser-safe frontend settings | `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` |

The canonical `MCP_RESOURCE_URL` remains
`https://facebook-page-operations-api.onrender.com/mcp`. Existing exact file-host
allowlisting and bounded credential-free HTTPS downloads still apply. If actual
image transfer requires a different provider host, verify it separately before
changing `MCP_FILE_ALLOWED_HOSTS`; do not broaden it to arbitrary image URLs.
No new frontend environment variable or Supabase migration is needed.

## Local review evidence — 1 November 2026

The existing draft PR's baseline was independently reproduced: **114 backend
tests**, **12 frontend consent tests**, and the production build passed.
Additional checks cover verified client matching, every protected REST route,
existing-client compatibility, forbidden actions before side effects, bridge
replays/conflicts/concurrency/pending reservations, callback tricks and consent
ordering, corrupt upload/stored bytes and dry-run zero-publishing behavior.
Final results: **156 backend tests passed**, **15 frontend consent tests passed**,
Python compilation and dependency consistency checks passed, and the frontend
production build passed. The unchanged frontend lockfile reports four existing
development-tool dependency audit findings (three high, one low); `npm audit`
is not clean. Dependency upgrades are outside this bridge change.

Run from `backend`: `.venv/bin/python -m pytest` and
`.venv/bin/python -m compileall -q app tests`.
Run from `frontend`: `npm test` and `npm run build`.
Tests use isolated SQLite, fake private storage, synthetic OAuth tokens and
mocked Meta boundaries. They do not access hosted secrets or publish to Facebook.
This review does not register clients, change hosted settings, deploy or merge.
