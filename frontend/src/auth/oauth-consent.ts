import type { OAuthAuthorizationDetails, OAuthRedirect, SupabaseClient } from "@supabase/supabase-js";

type ConsentProvider = Pick<SupabaseClient["auth"]["oauth"], "getAuthorizationDetails" | "approveAuthorization" | "denyAuthorization">;
type VerifyOperator = () => Promise<unknown>;

export function chatgptRedirect(value: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.hostname !== "chatgpt.com" || url.username || url.password
    || !(url.pathname.startsWith("/connector/oauth/") || url.pathname === "/connector_platform_oauth_redirect")) {
    throw new Error("This connection must return to ChatGPT. Start it again from the private plugin.");
  }
  return url.href;
}

function validateAuthorizationId(value: string | null): asserts value is string {
  if (!value || !/^[0-9a-f-]{36}$/i.test(value)) {
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
    chatgptRedirect(data.redirect_uri);
    return data;
  }
  return { redirect_url: chatgptRedirect(data.redirect_url) };
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
  return chatgptRedirect(result.data.redirect_url);
}

export function passwordSetupReturnUrl(pathname: string, search: string): string {
  const authorizationId = new URLSearchParams(search).get("authorization_id");
  const query = pathname === "/oauth/consent" && authorizationId
    ? `?${new URLSearchParams({ authorization_id: authorizationId })}`
    : "";
  return `${pathname}${query}`;
}
