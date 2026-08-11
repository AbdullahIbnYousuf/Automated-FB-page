import { useSystemStatus } from "../state/SystemStatusContext";

export function ModeBanner() {
  const { backendState, status } = useSystemStatus();

  if (backendState === "loading") {
    return (
      <div className="mode-banner mode-banner--checking" aria-live="polite">
        <span className="mode-banner__signal" />
        <span>
          <strong>Checking backend</strong>
          <small>Confirming the operating mode</small>
        </span>
      </div>
    );
  }

  if (backendState === "unavailable" || !status) {
    return (
      <div className="mode-banner mode-banner--offline" role="alert">
        <span className="mode-banner__signal" />
        <span>
          <strong>Backend unavailable</strong>
          <small>System health and publishing state are unknown</small>
        </span>
      </div>
    );
  }

  const isDryRun = status.publish_mode === "dry_run";
  const title = isDryRun ? "Dry run" : "Facebook scheduling";
  const detail = status.publishing_enabled
    ? "Publishing enabled"
    : "Publishing disabled";

  return (
    <div
      className={`mode-banner ${
        status.publishing_enabled
          ? "mode-banner--enabled"
          : "mode-banner--safe"
      }`}
      aria-live="polite"
    >
      <span className="mode-banner__signal" />
      <span>
        <strong>{title}</strong>
        <small>{detail}</small>
      </span>
    </div>
  );
}
