# ChatGPT image transfer diagnosis — 1 November 2026

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
