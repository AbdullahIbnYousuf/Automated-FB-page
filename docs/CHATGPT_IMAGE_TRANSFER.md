# ChatGPT image transfer diagnosis

## Generated-image investigation — 2 November 2026

Inspected current main and the live backend at
`c1370d1070a879a0948b0dccf6a343bd0a3f5f89`, plus the private Sites bridge
source at `be415b37332d002836facd7067ea16ff7a0f8032` (version 4).
The bridge declares the complete `openai/fileParams` object schema and forwards
the image object unchanged to the backend's `create_post`. The backend accepts
the same object for uploaded and generated images. This follows the
[official file-input contract](https://developers.openai.com/plugins/reference).
Bare file IDs and sandbox paths are not backend download URLs; do not invent
URLs or add a separate OpenAI credential to resolve them.

The two production rejection events at **02:09:20Z** and **02:15:53Z** on
2 November both report exactly:

```json
{"rejection_category":"host_not_allowed","hostname":"oaisdmntprcentralindia.blob.core.windows.net","redirect_hop":0}
```

These align with the user's two reported generated-image failures. The backend
received a parseable HTTPS URL; hostname validation rejected it before DNS or
download. The error was not evidence of an unresolved file ID or DNS failure.
Diagnostics deliberately omit file IDs, so they cannot independently associate
each event with one of the two reported references. A public Azure DNS answer
establishes the storage service, not an independent OpenAI ownership attestation;
the provenance evidence is the reported ChatGPT transfer plus these events.

The saved Render override contained the three previously verified exact hosts.
After adding the observed Azure host, a fresh built-in generated-image test at
**02:39:27Z** reached the backend with a different exact delivery hostname:
`sdmntprindiasocentral.oaiusercontent.com`. Its sanitized diagnostic was also
`host_not_allowed` at hop 0. This independently confirms that generated content
is resolved into a downloadable file object; delivery can use distinct exact hosts.
That test ended with a recorded rejection and a subsequent list still contained
exactly four posts, so no pending/ambiguous creation was retried.

A new test after that configuration became live at **02:42:51Z** reported
`host_not_allowed` at hop 0 for `sdmntprcentralindia.oaiusercontent.com`.
It also completed with rejection and no new post. Each new acceptance request
was made only after verifying the previous rejection created no post; pending
or ambiguous requests were never replayed with replacement keys.

The final configuration-only fix appends those three observed exact hosts:

```env
MCP_FILE_ALLOWED_HOSTS=files.oaiusercontent.com,sdmntprnznorth.oaiusercontent.com,oaisdmntprnznorth.blob.core.windows.net,oaisdmntprcentralindia.blob.core.windows.net,sdmntprindiasocentral.oaiusercontent.com,sdmntprcentralindia.oaiusercontent.com
```

Do not add `*.blob.core.windows.net`, other Azure storage accounts, regional
patterns, or a suffix-matching rule. No downloader, bridge runtime, database or
Storage change is required. The repository/Blueprint keeps its conservative
default; the explicit production override is managed on the existing Render
service. A future Blueprint sync must preserve that override intentionally.
Further regional delivery hosts require fresh sanitized evidence and review.

Only `MCP_FILE_ALLOWED_HOSTS` changes. Preserve the live-capability settings
authorized separately on 1 November: `AUTOMATION_ENABLED=true`,
`PUBLISH_MODE=facebook_schedule`, `AUTH_REQUIRED=true`,
`MCP_BRIDGE_ALLOW_LIVE_SCHEDULING=true`, and the existing `MCP_BRIDGE_CLIENT_ID`.
File transfer/dry-run acceptance never authorizes a real Meta write.

`tests/test_generated_image_transfer.py` covers the observed rejection before
configuration, exact-host lookalike rejection, HTTPS/port/fragment restrictions,
private/mixed DNS answers, redirect rejection, full malformed-image rejection,
byte-for-byte private-storage persistence, retrieval, replay without redownload,
and explicit dry-run with no Meta write even when live gates are enabled.

Local checks: **261 backend tests**, including **26 new transfer regressions**;
**15 frontend consent tests**; Python compilation and dependency consistency;
frontend production build; **26 existing Sites bridge tests**, Worker build and
artifact validation. All passed. Local HTTP, Storage and Meta operations are
isolated mocks. No frontend or Sites runtime source change is needed.

### Hosted acceptance

The final configuration deployment `dep-dbjvhudg1s2s738sc910` became live at
**02:45:51Z** on 2 November, using unchanged backend commit `c1370d1`.
A newly generated built-in image (red paper sailboat, “TRANSFER TEST”) then
passed `create_post` directly from its generated local file reference, without
manual download/re-upload or user intervention. It created exactly one draft:

- Post: `bf25739b-337a-4b77-9f4f-ec307cf73742`.
- Created: **02:46:20Z**; retrieved through bridge `get_post` as `draft`.
- Validated MIME: `image/png`; original generated filename retained.
- Private dashboard image loaded at **1254×1254**, visually matching the generated
  source. This confirms actual stored image retrieval, not just a file reference.
- Explicit bridge dry-run succeeded at **02:47:19Z** with `simulated=true`,
  `external_request_made=false`, `facebook_object_id=null`; one persisted attempt
  and status `ready` on subsequent retrieval.
- Post count increased **4 → 5**, with the existing four records unchanged.

Byte-for-byte persistence is asserted by the isolated integration tests. Hosted
verification checked successful transfer, authenticated image display, dimensions
and visual match; it did not independently compare a production byte digest
(the browser's asset export could not fetch the protected media).
The two older conversation file IDs were not directly resolved in this Codex
environment; the fresh built-in generated-image test establishes the supported
transfer path. Future unobserved delivery hosts still fail closed.

Live publishing/authentication gates and bridge restrictions remained unchanged.
No real scheduling tool or Meta publishing request was called. Any real post
still requires separate approval of its exact caption, image, Page and future
local time. Unknown write outcomes remain blocked without automatic retries.

### Historical diagnostic rollout — 1 November 2026

The sections below record the earlier default-host investigation and its then
pending acceptance steps. They do not describe current hosted publishing gates
or the generated-image rejection confirmed above.

## What was observed

- Inspected current `main`, commit `2f12102`, which merges PR #1.
- The Render Dashboard identifies that same commit as the last successfully
  deployed commit on `facebook-page-operations-api`.
- Authenticated bridge status returned `bridge_client_restricted=true`,
  `authentication_required=true`, `automation_enabled=false`,
  `publish_mode=dry_run`, and `publishing_enabled=false`.
- Read the service's environment-variable **names**, without revealing values.
  There is no `MCP_FILE_ALLOWED_HOSTS` override and no linked environment group.
  The deployed code's default is therefore `files.oaiusercontent.com`.
- The reported saved-PNG and new-PNG failures return `FILE_URL_NOT_ALLOWED`.
  Current code maps URL parsing, URL policy and DNS failures to that same code.
  The queried Render application logs contain no matching rejection details.

**The actual transferred hostname, redirect chain and production rejection
category could not be observed in this environment. An allowlist mismatch is
not confirmed. No exact hosted configuration change can yet be justified.**
No sample signed URL was requested, logged, saved or invented, and no production
draft creation or scheduling attempt was made during this repository review.

## Repository change

The downloader now emits one structured `mcp_file_url_rejected` warning at the
failing check. Its only diagnostic values are:

- `rejection_category`: a fixed category from the table below;
- `hostname`: a bounded, lowercase/IDNA hostname or canonical IP literal, or
  null when the authority cannot safely be represented;
- `redirect_hop`: zero for the original URL, one for its first redirect, etc.

No URL, URL path, query string, fragment, userinfo, file ID, authorization header,
token, DNS answer or exception text is included. The JSON logger explicitly
permits these three fields. Client responses retain the existing generic error.

| Category | Meaning and next step |
| --- | --- |
| `url_parse_error` | Invalid URL authority/port or malformed redirect; inspect the bridge's file-object transfer without copying the signed URL. |
| `scheme_not_https` | Non-HTTPS input, including sandbox paths, is not downloadable file delivery. Fix the transfer contract; do not add a host. |
| `userinfo_not_allowed`, `fragment_not_allowed`, `port_not_allowed` | The supplied URL violates policy. Preserve the checks. |
| `host_not_allowed` | Only now investigate this exact observed hostname and hop as a possible verified file-delivery host. |
| `dns_lookup_failed` | The configured host could not be resolved. Investigate DNS from the Render runtime; changing the allowlist does not fix this. |
| `dns_no_addresses`, `dns_invalid_address` | DNS did not return usable addresses. Do not bypass validation. |
| `dns_non_public` | At least one address is non-public; keep it blocked, including mixed public/private answers. |

Malformed redirect joining now returns the same sanitized policy error instead
of an internal error. Exact host matching, HTTPS/port restrictions, all-address
public DNS checks, per-hop validation, three-request bound, time/byte limits,
credential-free downloads, image decoding and durable request protection remain
in place. No delivery hostname was added or removed.

## Remaining acceptance

1. Review and separately authorize deployment of these diagnostics. This task
   does not merge, deploy or alter hosted settings.
2. Make one explicitly intended draft-only attempt with a real attached PNG.
   Read only its rejection category, hostname and hop from the diagnostic event.
   Do not paste signed URLs, raw tool frames or credentials into logs or chat.
3. If the category is `host_not_allowed`, verify ownership and the actual
   ChatGPT file-delivery use of that exact host. Only then propose the complete,
   comma-separated `MCP_FILE_ALLOWED_HOSTS` value on the **existing backend**,
   preserving any other verified required hosts. Validate every redirect hop.
   Do not allow arbitrary URLs, wildcard domains or broad cloud-storage domains.
   Other categories require their corresponding transfer/DNS correction.
4. Account for durable replay before another attempt: a completed
   `FILE_URL_NOT_ALLOWED` with no post association is recorded and replayed even
   if its signed URL changes. Verify no draft was created before initiating a
   fresh intended acceptance request with a new key. Reuse keys on transport
   retries; never change keys to bypass a pending or ambiguous operation.
5. Confirm draft retrieval and actual private image persistence, then explicitly
   dry-run that existing post. Verify `simulated=true`,
   `external_request_made=false`, and no Facebook object ID.

Preserve `AUTOMATION_ENABLED=false`, `PUBLISH_MODE=dry_run`, `AUTH_REQUIRED=true`
and the existing `MCP_BRIDGE_CLIENT_ID` restriction. No new database, migration,
storage bucket or frontend setting is required. Hosted image transfer and dry-run
acceptance remain unverified; local tests do not establish either.

## Local checks

- Focused downloader/MCP suite: **95 passed**.
- Full backend suite: **202 passed**.
- Python compilation and dependency consistency: passed.
- Frontend consent suite: **15 passed**.
- Frontend production build: passed.

Regression tests distinguish policy and DNS categories, exercise malformed and
hostile URLs, private/mixed DNS answers and redirects, verify redaction in both
raw log records and emitted JSON, and confirm no draft or repeated download from
a recorded rejection. All network and persistence fixtures are isolated; no
real publishing request is made.
