# Desktop MCP connection diagnosis — 26 October 2026

Scope: repair connection/discovery only. No scheduling logic, Meta credentials,
publishing switches, application data or provider OAuth security settings changed.

## Verified failure

The installed/saved `0.1.0` package contained root `plugin.json`, root `mcp.json`,
generated `.codex-plugin/plugin.json`, `.mcp.json`, and the scheduling skill.
The portable root took precedence over the compatibility manifest. The server's
documented `extensions.com.openai.auth` field was rejected by the desktop parser.

The local desktop log database contains this warning for this exact plugin:

```text
failed to parse plugin MCP server
server="the-test-lab-operations"
error="unknown field `extensions`, expected `url` or `headers`"
```

Read-only `plugin/read` probes against the available native `codex-cli 0.147.0`
runtime reproduced it without installation, model turns or MCP tool execution:

| Package fixture | Parsed MCP servers |
| --- | --- |
| Original portable OAuth declaration | none; same parser warning |
| Portable declaration without extension (diagnostic control only) | `the-test-lab-operations` |
| Compatibility manifest + native HTTP + `scopes: ["email"]` | `the-test-lab-operations` |

Thus the skill could load while the server was dropped before OAuth started.
Changing transport spelling alone was not the cause or sufficient fix.
This matches the [upstream parser issue](https://github.com/openai/codex/issues/53658)
and [runtime implementation](https://github.com/openai/codex/blob/main/codex-rs/codex-mcp/src/agent_plugin_config.rs).

## Live HTTP and OAuth checks

- Backend health and scoped protected-resource metadata: HTTP 200, JSON.
- Anonymous `GET /mcp`, `POST /mcp` initialization and invalid-token `tools/list`:
  HTTP 401, JSON `invalid_token` / `Authentication required`.
- Challenge: `Bearer error="invalid_token"` with `resource_metadata` pointing to
  `https://facebook-page-operations-api.onrender.com/.well-known/oauth-protected-resource/mcp`.
- Supabase authorization-server discovery: HTTP 200, exact issuer
  `https://dqgaviukwfyaxqswraaf.supabase.co/auth/v1`, DCR registration endpoint,
  S256 PKCE, `email` and refresh-token support.
- A native OAuth diagnostic, using only transient CLI server configuration,
  successfully registered a client and built an authorization request containing
  the exact MCP resource, S256 challenge, `email offline_access` and a registered
  `http://127.0.0.1:<ephemeral-port>/callback/<nonce>` redirect.
- That authorization request returned HTTP 302 to the production frontend's
  `/oauth/consent?authorization_id=...`. No operator credentials were provided;
  the diagnostic expired waiting for consent. No access token was minted by
  this diagnostic and it did not authenticate the installed plugin.
- Sampled Render logs show the expected metadata/401 diagnostic requests and no
  authenticated MCP success. They do not establish the absence of every historical
  client attempt; the desktop parser warning establishes the pre-network failure.

## Fix published on the existing private identity

- Plugin `plugins_6ad1a1de4a448191873aba41eb265f96`, version `0.1.1`, release
  `pluginrel_6adf3fc4e258819198521b1004a212c5`.
- Retained the same private audience, endpoint, skill and presentation. Replaced
  the masking portable layout with the tested `.codex-plugin/plugin.json` and
  `.mcp.json` compatibility layout. Read-back confirms the portable files are
  absent and the native server has `type: "http"`, the original URL, and `email`.
- OAuth is still enforced by the backend. Native OAuth discovery/DCR replaces
  the rejected package extension; no API key, Bearer header or secret is bundled.
- The old consent guard would reject native loopback redirects after login.
  The fix accepts only provider-returned numeric `127.0.0.1` callbacks on ports
  1024–65535 with `/callback` or `/callback/<8–128-character nonce>`. It rejects
  credentials, fragments, other hosts, alternate IP spellings and other paths.
  Exact registration, operator verification, PKCE/state and JWT validation remain.
- Consent fix deployed to existing Pages production, preview
  `https://74b07ca6.facebook-page-operations-dashboard.pages.dev`;
  production bundle `index-CV2Hyjzw.js` verified over HTTP.
- Regression results: 111 backend/package tests, 10 frontend consent tests,
  frontend build/type checking, Python compilation and bundle secret-pattern scan passed.

## Remaining interactive acceptance

### Follow-up: opaque authorization ID validation

After updating the plugin, the operator reached the authentication flow but
the frontend displayed `Start the connection from ChatGPT to obtain a valid
authorization request`. A real Supabase authorization redirect contained a
32-character opaque ID; the frontend incorrectly required a 36-character UUID.
The format guard now accepts bounded URL-safe opaque IDs rather than assuming
UUID syntax. Supabase still validates the request after backend operator
verification; redirect restrictions and OAuth security are unchanged.

Added a regression test for loading, approving, denying and retaining a
32-character opaque ID through password setup, plus invalid-path/length cases.
All 11 consent tests and the production build/type check pass. A contract probe
with a real provider-issued ID confirms it passes the corrected guard without
printing the ID or authenticating an operator. Deployed to the existing Pages
project, preview `https://4a2e4bab.facebook-page-operations-dashboard.pages.dev`,
production bundle `index-5B8fDPC9.js`. No new plugin release is required.

Close the failed browser tab and start a fresh authentication request from the
existing Ubuntu plugin. Do not paste the authorization ID, code or tokens into
chat. Actual consent and authenticated tool calls remain interactive acceptance.

The application still cached `0.1.0` at the end of source inspection. Update or
refresh this existing plugin to `0.1.1` and fully restart the Ubuntu application.
Check Settings → MCP servers for its plugin-provided entry; use its native
sign-in action and approve operator consent in the browser. Do not reinstall,
create a second plugin, paste tokens or turn off authentication.

After the client has authenticated, verify `initialize`, all eight entries in
`tools/list`, then `tools/call` for `get_system_status` and
`test_facebook_connection`. These authenticated production calls are not claimed
complete by a parser test or mocked protocol test. Record their actual outcomes;
an expired Meta token would be a separate connection result, not missing MCP tools.
