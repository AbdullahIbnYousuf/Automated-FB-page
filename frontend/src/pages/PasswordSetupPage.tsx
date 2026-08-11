import { useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";

export function PasswordSetupPage() {
  const { updatePassword } = useAuth();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password.length < 8) {
      setError("Use at least 8 characters.");
      return;
    }
    if (password !== confirmation) {
      setError("The passwords do not match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await updatePassword(password);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Password setup failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="login-brand" aria-hidden="true">F</div>
        <span className="eyebrow">Operator invitation</span>
        <h1>Choose your password</h1>
        <p>This password is sent directly to Supabase and is never handled by our backend.</p>
        {error ? <div className="login-error" role="alert">{error}</div> : null}
        <form onSubmit={(event) => void submit(event)}>
          <div className="field-group">
            <label htmlFor="new-password">New password</label>
            <input id="new-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} disabled={submitting} />
          </div>
          <div className="field-group">
            <label htmlFor="confirm-password">Confirm password</label>
            <input id="confirm-password" type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={submitting} />
          </div>
          <button className="primary-button login-submit" type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Save password"}
          </button>
        </form>
      </section>
    </main>
  );
}
