# ChatGPT MCP connection — The Test Lab Operations

## Components and endpoint

The existing Render FastAPI service hosts the official Python MCP SDK at:

`https://facebook-page-operations-api.onrender.com/mcp`

The endpoint uses stateless Streamable HTTP with JSON responses. It supports
current MCP and compatible older protocol versions. It is OAuth protected,
including initialization and tool discovery. A 401 with `WWW-Authenticate` is
expected before linking, not evidence of an unauthenticated publishing endpoint.

Public resource discovery:

`https://facebook-page-operations-api.onrender.com/.well-known/oauth-protected-resource/mcp`

Authorization-server issuer:

`https://dqgaviukwfyaxqswraaf.supabase.co/auth/v1`

Supabase discovery:

`https://dqgaviukwfyaxqswraaf.supabase.co/.well-known/oauth-authorization-server/auth/v1`

Tools: `get_system_status`, `test_facebook_connection`, `list_posts`, `get_post`,
`create_post`, `update_post`, `schedule_post`, `create_and_schedule_post`.
OAuth policy is published in each tool's `_meta.securitySchemes`, the supported
OpenAI compatibility metadata, and enforced independently on every HTTP request.

## Deployment sequence

1. Install backend dependencies with `python -m pip install -e '.[dev]'`.
2. Link the existing Supabase project and apply committed migrations with
   `supabase db push`. Never reset the hosted database.
3. Build/deploy the existing frontend with its three browser-safe Vite variables.
   `/oauth/consent` must load directly on Cloudflare Pages.
4. Deploy the same Render service. Keep `AUTH_REQUIRED=true`,
   `AUTOMATION_ENABLED=false`, `PUBLISH_MODE=dry_run`. Set:

   ```env
   MCP_RESOURCE_URL=https://facebook-page-operations-api.onrender.com/mcp
   MCP_FILE_ALLOWED_HOSTS=files.oaiusercontent.com
   MCP_FILE_TIMEOUT_SECONDS=20
   ```

5. In Supabase Authentication → OAuth Server enable OAuth 2.1, set authorization
   path `/oauth/consent`, and enable dynamic registration. Keep the Auth Site URL
   `https://facebook-page-operations-dashboard.pages.dev` and public signup disabled.
6. In Authentication → Hooks enable the PostgreSQL Custom Access Token hook
   `public.scheduler_mcp_access_token_hook`. Apply only after its migration exists.
   Local reproducible settings are in `supabase/config.toml`; review differences
   before a whole-project `supabase config push` so unrelated hosted settings are preserved.
7. Verify discovery, anonymous 401 responses, operator login and OAuth consent.

The project already has an ES256 signing key. No secret JWT signing key is needed
by this backend. The hook adds the canonical MCP audience to OAuth access tokens
with the granted `email` scope; non-OAuth dashboard tokens remain unchanged.
OAuth refresh carries the client and granted scopes forward, so the hook also
binds refreshed tokens. This project's OAuth consent is dedicated to this
scheduler; review the hook before introducing any unrelated OAuth application.
Only the configured operator email is accepted, regardless of which clients
register. Registration by itself grants no account or tool access.

## Connect in ChatGPT web

1. Open ChatGPT Plugins → plus → **Add custom MCP server**.
2. Name it **The Test Lab Operations** and enter the `/mcp` URL above.
3. Choose OAuth and dynamic client registration. Use the `email` scope. No
   operator password, Page token or database key belongs in the plugin configuration.
4. Create the private plugin, install it, and select Connect. Complete login with
   the existing operator account on our Pages frontend and review Allow/Deny.
5. Start a chat, select this plugin with `@`, and ask for system status and the
   Facebook connection test.

Alternatively, upload the portable package under `plugins/the-test-lab-operations`
through the supported private-plugin creation tool. It contains `plugin.json`,
`mcp.json` and workflow instructions; it does not deploy the server or complete
the operator's consent. Reuse an existing matching plugin rather than creating
duplicates. Record the returned plugin ID and URL in the acceptance evidence.

Supabase manages DCR callback registration. Do not guess a callback URL. If
manually registering a client, use the exact callback shown in ChatGPT's MCP
management screen. The consent page accepts only Supabase-returned HTTPS
ChatGPT callback URLs and never a model/user-supplied redirect.

## Images and replay behavior

Creation tools mark the top-level `image` parameter with `openai/fileParams`.
Its schema declares all four string properties: required `download_url` and
`file_id`, optional `mime_type` and `file_name`. ChatGPT supplies the temporary
download location; a sandbox path or invented URL is insufficient.

The backend downloads bytes without application credentials, permits only exact
configured HTTPS hosts with public DNS answers, checks each redirect, bounds
time and size, and uses the same JPEG/PNG validation/private Storage as the GUI.
Signed URLs are not stored, returned or logged. Missing optional metadata is
derived from decoded bytes. Original-file metadata, when supplied, must agree.

If a legitimate ChatGPT client uses another file host, verify the actual provider
host without revealing the signed query and add that exact hostname to
`MCP_FILE_ALLOWED_HOSTS`. Never allow arbitrary domains or wildcard cloud-storage
domains. An expired URL must be replaced by reattaching/selecting the image.
If client transfer is unavailable, save the image through the dashboard, then
use `list_posts`/`get_post` and `schedule_post` for that existing ID. Record uploaded
and generated image verification separately; mock downloads prove neither.

Use a unique `request_key` for one intended creation and reuse it on retries.
The database reserves operator + tool + key before side effects and records a
fingerprint, post association and safe result. Changing the signed download URL
does not change the fingerprint; changing content/file ID/time does. A replay
never starts a new Facebook request. An unfinished key after a process crash
stays blocked for operator inspection; there is no automatic takeover/recovery.

Scheduling tools default to `dry_run`, even if backend live mode is enabled.
Explicit `facebook_schedule` requires both publishing switches and never silently
returns a simulation. The dashboard retains its environment-selected behavior.
All results identify simulation, external request, attempt and Meta reference.

## Tests and acceptance

### Rollout evidence — 16 October 2026

- Implementation commit: `1d9578d` (pushed to `main`). Backend tests: 109 passed;
  frontend consent tests: 8 passed. Python compilation, dependency checks and
  the frontend production build/type check passed.
- The existing Render service deployed through its GitHub integration. Public
  MCP resource metadata returned HTTP 200; an unauthenticated MCP initialize
  request returned HTTP 401 with the canonical resource-metadata challenge.
  Authenticated live tool discovery remains unverified.
- The local production preview showed the signed-out consent login while
  retaining `authorization_id`. Public legal pages loaded without login;
  the data-deletion page survived refresh. A 375-pixel viewport showed no
  horizontal overflow, and the checked routes had no console errors.
- The private plugin package was saved once:
  [The Test Lab Operations](https://chatgpt.com/plugins/plugins_6ad1a1de4a448191873aba41eb265f96)
  (`plugins_6ad1a1de4a448191873aba41eb265f96`, version `0.1.0`). Saving the
  package is not installation, operator authorization or live tool verification.
- Supabase authorization-server discovery still returned HTTP 404 with
  `feature_disabled`. Supabase migrations/hook/OAuth configuration and the
  Cloudflare consent-frontend rollout remain pending renewed provider access.
  Render, Supabase and Cloudflare CLI credentials had expired; Render's
  automatic deployment did not restore administrative CLI access.
- Live OAuth login/denial/refresh, uploaded-image transfer, generated-image
  transfer and authenticated dry-run scheduling have not been accepted yet.
  No real Facebook scheduling request was made for this integration. Runtime
  publishing settings must be inspected before the controlled acceptance test;
  safe deployment defaults remain committed in configuration.

Run backend tests with `cd backend && .venv/bin/python -m pytest` and compile with
`.venv/bin/python -m compileall -q app tests`. Run frontend build/type checking
with `cd frontend && npm run build`; run the consent-flow checks with `npm test`.
Test real authentication through HTTP;
an in-memory MCP client can bypass transport authentication.

Record these stages individually:

1. Deployed HTTPS metadata/401 and dashboard/public-route regression checks.
2. ChatGPT private plugin discovery, login/consent, token refresh and tool execution.
3. An uploaded image and a generated image actually transferred, saved and retrievable.
4. Dry-run creation/scheduling and recorded `external_request_made=false`.
5. An exact test caption/image/Page/time approved by the operator.
6. One real scheduling call accepted by Meta with its returned ID stored.
7. Status retrieved through ChatGPT and the operator's visual confirmation in
   Meta Business Suite Planner. The application never automates Facebook's UI.

For the live test choose roughly 30 minutes ahead in Asia/Dhaka. Verify the
current official Meta photo contract/window, then enable both Render switches
only after explicit approval. Submit once and do not automatically retry. Return
to safe defaults after the controlled test unless the operator asks otherwise.

Disconnect/revoke the client's grant in Supabase or the ChatGPT connection
settings. Refresh tokens stop working after revocation; already-issued access
tokens can remain valid until their expiry. Never paste those tokens into chat.

Official references: [OpenAI authentication](https://developers.openai.com/plugins/build/auth),
[file inputs](https://developers.openai.com/plugins/reference#define-file-inputs),
[ChatGPT connection](https://developers.openai.com/api/docs/guides/custom-mcp-server),
[Supabase OAuth](https://supabase.com/docs/guides/auth/oauth-server),
[token hooks](https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook),
[MCP ASGI mounting](https://py.sdk.modelcontextprotocol.io/run/asgi/).
