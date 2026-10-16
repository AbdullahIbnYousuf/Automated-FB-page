import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import type { OAuthAuthorizationDetails } from "@supabase/supabase-js";

import { apiRequest } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { supabase } from "../auth/supabase";
import { decideConsent, loadConsent } from "../auth/oauth-consent";

const verifyOperator = () => apiRequest("/api/system/status");

export function OAuthConsentPage() {
  const location = useLocation();
  const { signOut } = useAuth();
  const authorizationId = new URLSearchParams(location.search).get("authorization_id");
  const [details, setDetails] = useState<OAuthAuthorizationDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!supabase) throw new Error("Authentication is unavailable.");
      // A browser session alone is insufficient: verify the backend operator allowlist first.
      const data = await loadConsent(authorizationId, verifyOperator, supabase.auth.oauth);
      if (!active) return;
      if (!("authorization_id" in data)) {
        window.location.assign(data.redirect_url);
        return;
      }
      setDetails(data);
    }
    void load().catch((caught: unknown) => {
      if (active) setError(caught instanceof Error ? caught.message : "Authorization is unavailable.");
    });
    return () => { active = false; };
  }, [authorizationId]);

  async function decide(approve: boolean) {
    if (!authorizationId || !supabase || !details || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const destination = await decideConsent(authorizationId, approve, verifyOperator, supabase.auth.oauth);
      window.location.assign(destination);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authorization failed.");
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card consent-card">
        <div className="login-brand" aria-hidden="true">F</div>
        <span className="eyebrow">The Test Lab Operations</span>
        <h1>Connect to ChatGPT</h1>
        {error ? <div className="login-error" role="alert">{error}</div> : null}
        {!details && !error ? <p role="status">Verifying the operator and connection request…</p> : null}
        {details ? <>
          <p><strong>{details.client.name || "ChatGPT"}</strong> is requesting access as {details.user.email}.</p>
          <p>This connection can:</p>
          <ul className="consent-capabilities">
            <li>Read configuration, posts and scheduling history.</li>
            <li>Test the Facebook connection for The Test Lab.</li>
            <li>Save captions and attached images, and edit eligible drafts.</li>
            <li>Schedule approved content when real publishing is enabled.</li>
          </ul>
          <p>Identity scope: <strong>{details.scope}</strong>. Publishing switches and duplicate protection still apply. Passwords and Facebook credentials are never shared with ChatGPT.</p>
          <div className="form-actions">
            <button className="secondary-button" type="button" disabled={submitting} onClick={() => void decide(false)}>Deny</button>
            <button className="primary-button" type="button" disabled={submitting} onClick={() => void decide(true)}>{submitting ? "Saving…" : "Allow connection"}</button>
          </div>
        </> : null}
        <button className="consent-signout" type="button" disabled={submitting} onClick={() => void signOut()}>Use a different account</button>
      </section>
    </main>
  );
}
