import { useSystemStatus } from "../state/SystemStatusContext";

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
  const { backendState, status } = useSystemStatus();
  const unavailable = backendState !== "available" || !status;

  return (
    <div className="page-stack">
      <section className="section-panel section-panel--intro">
        <span className="eyebrow">Read-only configuration</span>
        <h2>Settings / Connection</h2>
        <p>
          This page reports safe backend configuration only. Credentials cannot
          be entered, viewed, changed, or validated from the browser.
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
              : status.facebook.page_id_configured
                ? "Configured"
                : "Not configured"
          }
          detail="Only configuration presence is exposed"
        />
        <ConfigurationRow
          label="Page access token"
          value={
            unavailable
              ? "Unknown"
              : status.facebook.access_token_configured
                ? "Configured"
                : "Not configured"
          }
          detail="The token value remains backend-only"
        />
        <ConfigurationRow
          label="Publish mode"
          value={status?.publish_mode.replaceAll("_", " ") ?? "Unknown"}
          detail="Real writes require two explicit backend switches"
        />
        <ConfigurationRow
          label="Graph API version"
          value={status?.graph_api_version ?? "Unknown"}
          detail="Informational only; no Facebook client exists in Phase 2/3"
        />
        <ConfigurationRow
          label="Application timezone"
          value={status?.timezone ?? "Unknown"}
          detail="Future local schedule input will use this IANA timezone"
        />
      </section>
    </div>
  );
}
