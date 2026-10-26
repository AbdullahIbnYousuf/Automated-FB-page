import type { OAuthAuthorizationDetails, OAuthRedirect, SupabaseClient } from "@supabase/supabase-js";

type ConsentProvider = Pick<SupabaseClient["auth"]["oauth"], "getAuthorizationDetails" | "approveAuthorization" | "denyAuthorization">;
type VerifyOperator = () => Promise<unknown>;

// Only call with a redirect returned by Supabase after operator verification.
// Supabase binds it to the client's exact registered URI; PKCE/state are enforced
// by the OAuth client. Native Codex uses an ephemeral numeric loopback listener.
export function oauthRedirect(value: string): string {
  const url = new URL(value);
  const web = url.protocol === "https:" && url.hostname === "chatgpt.com" && !url.port
    && (url.pathname.startsWith("/connector/oauth/") || url.pathname === "/connector_platform_oauth_redirect");
  const native = value.startsWith("http://127.0.0.1:") && url.protocol === "http:"
    && url.hostname === "127.0.0.1" && Number(url.port) >= 1024 && Number(url.port) <= 65535
    && /^\/callback(?:\/[A-Za-z0-9_-]{8,128})?$/.test(url.pathname);
  if (url.username || url.password || url.hash || !(web || native)) {
    throw new Error("This connection must return to ChatGPT or its native OAuth callback. Start it again from the private plugin.");
  }
  return url.href;
}

function validateAuthorizationId(value: string | null): asserts value is string {
  // Supabase currently issues opaque 32-character IDs, not UUIDs. Bound and
  // constrain the path segment here; only Supabase can validate the request.
  if (!value || !/^[A-Za-z0-9_-]{1,128}$/.test(value)) {
    throw new Error("Start the connection from ChatGPT to obtain a valid authorization request.");
  }
}

export async function loadConsent(
  authorizationId: string | null, verifyOperator: VerifyOperator, provider: ConsentProvider,
): Promise<OAuthAuthorizationDetails | OAuthRedirect> {
  validateAuthorizationId(authorizationId);
  await verifyOperator();
  const { data, error } = await provider.getAuthorizationDetails(authorizationId);
  if (error || !data) throw new Error("The authorization request is invalid or expired. Start the connection again in ChatGPT.");
  if ("authorization_id" in data) {
    oauthRedirect(data.redirect_uri);
    return data;
  }
  return { redirect_url: oauthRedirect(data.redirect_url) };
}

export async function decideConsent(
  authorizationId: string, approve: boolean, verifyOperator: VerifyOperator, provider: ConsentProvider,
): Promise<string> {
  validateAuthorizationId(authorizationId);
  await verifyOperator();
  const result = approve
    ? await provider.approveAuthorization(authorizationId, { skipBrowserRedirect: true })
    : await provider.denyAuthorization(authorizationId, { skipBrowserRedirect: true });
  if (result.error || !result.data) throw new Error("The decision could not be saved. Restart the connection in ChatGPT.");
  return oauthRedirect(result.data.redirect_url);
}

export function passwordSetupReturnUrl(pathname: string, search: string): string {
  const authorizationId = new URLSearchParams(search).get("authorization_id");
  const query = pathname === "/oauth/consent" && authorizationId
    ? `?${new URLSearchParams({ authorization_id: authorizationId })}`
    : "";
  return `${pathname}${query}`;
}
