import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { configurationError, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError("Enter the authorized operator email and password.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="login-brand" aria-hidden="true">F</div>
        <span className="eyebrow">Facebook Page Operations</span>
        <h1>Operator sign in</h1>
        <p>Use the single authorized Supabase account to open the dashboard.</p>

        {configurationError || error ? (
          <div className="login-error" role="alert">
            {configurationError ?? error}
          </div>
        ) : null}

        <form onSubmit={(event) => void submit(event)}>
          <div className="field-group">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              autoComplete="username"
              inputMode="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting || Boolean(configurationError)}
            />
          </div>
          <div className="field-group">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={submitting || Boolean(configurationError)}
            />
          </div>
          <button
            className="primary-button login-submit"
            type="submit"
            disabled={submitting || Boolean(configurationError)}
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <small>Public registration is not available.</small>
        <nav className="public-links" aria-label="Legal and support">
          <Link to="/privacy">Privacy</Link>
          <Link to="/data-deletion">Data deletion</Link>
        </nav>
      </section>
    </main>
  );
}
