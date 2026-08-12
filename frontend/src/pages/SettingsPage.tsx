import { useState } from "react";

import { ApiError } from "../api/client";
import { useSystemStatus } from "../state/SystemStatusContext";
import type { FacebookConnectionStatus } from "../types/facebook";

function ConfigurationRow({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="configuration-row">
      <div>
        <strong>{label}</strong>
        <small>{detail}</small>
      </div>
      <span>{value}</span>
    </div>
  );
}

export function SettingsPage() {
  const {
    backendState,
    facebookConnection,
    status,
    testFacebookConnection,
  } = useSystemStatus();
  const [testing, setTesting] = useState(false);
  const [feedback, setFeedback] = useState<FacebookConnectionStatus | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const unavailable = backendState !== "available" || !status;

  async function runConnectionTest() {
    setTesting(true);
    setFeedback(null);
    setRequestError(null);
    try {
      setFeedback(await testFacebookConnection());
    } catch (caught) {
      setRequestError(
        caught instanceof ApiError
          ? caught.message
          : "The Facebook connection test could not be completed.",
      );
    } finally {
      setTesting(false);
    }
  }

  const activeResult = feedback ?? facebookConnection;
  const connectionLabel = activeResult?.connected
    ? "Connected"
    : activeResult?.status === "not_configured"
      ? "Not configured"
      : activeResult?.status === "not_verified"
        ? "Not verified"
        : activeResult
          ? "Error"
          : "Unknown";

  return (
    <div className="page-stack">
      <section className="section-panel section-panel--intro">
        <span className="eyebrow">Backend-controlled configuration</span>
        <h2>Settings / Connection</h2>
        <p>
          Credentials remain backend-only. The connection test remains read-only;
          real scheduling is controlled separately by both backend safety switches.
        </p>
      </section>

      <section className="configuration-panel">
        <ConfigurationRow
          label="Supabase"
          value={
            unavailable
              ? "Unknown"
              : status.supabase_configured
                ? "Configured"
                : "Not configured"
          }
          detail="PostgreSQL, private Storage, and Auth are backend-controlled"
        />
        <ConfigurationRow
          label="Dashboard authentication"
          value={status?.authentication_required ? "Required" : "Disabled"}
          detail="Hosted mode fails closed unless operator authentication is enabled"
        />
        <ConfigurationRow
          label="Page ID"
          value={
            unavailable
              ? "Unknown"
              : facebookConnection?.page_id_configured
                ? "Configured"
                : "Missing"
          }
          detail="Only configuration presence is exposed"
        />
        <ConfigurationRow
          label="Page access token"
          value={
            unavailable
              ? "Unknown"
              : facebookConnection?.access_token_configured
                ? "Configured"
                : "Missing"
          }
          detail="The token value remains backend-only"
        />
        <ConfigurationRow
          label="Connection"
          value={connectionLabel}
          detail="Last explicit read-only Meta connection result"
        />
        {activeResult?.page ? (
          <ConfigurationRow
            label="Connected Page"
            value={activeResult.page.name}
            detail={`Page ID ${activeResult.page.id}`}
          />
        ) : null}
        <ConfigurationRow
          label="pages_manage_posts"
          value="Expected"
          detail="Meta enforces this permission on a real write; the browser does not inspect the token"
        />
        <ConfigurationRow
          label="Graph API version"
          value={activeResult?.api_version ?? status?.graph_api_version ?? "Unknown"}
          detail="Explicitly versioned Page identity and scheduled-photo requests"
        />
        <ConfigurationRow
          label="Publish mode"
          value={status?.publish_mode?.replaceAll("_", " ") ?? "Unknown"}
          detail="Selected by backend configuration, never by the browser"
        />
        <ConfigurationRow
          label="Automation"
          value={status?.automation_enabled ? "Enabled" : "Disabled"}
          detail="The independent external-write safety switch"
        />
        <ConfigurationRow
          label="Real scheduling enabled"
          value={status?.publishing_enabled ? "Yes" : "No"}
          detail="Yes only when automation and Facebook scheduling mode are both enabled"
        />
        <ConfigurationRow
          label="Application timezone"
          value={status?.timezone ?? "Unknown"}
          detail="Future local schedule input will use this IANA timezone"
        />
      </section>

      <section className="section-panel connection-test-panel">
        <div>
          <span className="eyebrow">Facebook Page</span>
          <h2>Test Facebook Connection</h2>
          <p>
            This test is read-only. It will not publish, edit, schedule, or
            delete Facebook content.
          </p>
        </div>
        <button
          className="primary-button"
          type="button"
          disabled={unavailable || testing}
          onClick={() => void runConnectionTest()}
        >
          {testing ? "Testing connection…" : "Test Facebook Connection"}
        </button>
      </section>

      {requestError || feedback ? (
        <section
          className={`notice ${feedback?.connected ? "" : "notice--error"}`.trim()}
          role="status"
        >
          <div className="notice__icon">{feedback?.connected ? "✓" : "!"}</div>
          <div>
            <h3>{feedback?.connected ? "Connected" : "Connection not verified"}</h3>
            <p>{requestError ?? feedback?.message}</p>
          </div>
        </section>
      ) : null}
    </div>
  );
}
