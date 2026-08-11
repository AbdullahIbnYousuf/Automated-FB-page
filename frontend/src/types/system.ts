import type { FacebookConnectionStatus } from "./facebook";

export type PublishMode = "dry_run" | "facebook_schedule";

export interface HealthStatus {
  status: "ok";
  service: string;
}

export interface FacebookConfigurationStatus {
  page_id_configured: boolean;
  access_token_configured: boolean;
  fully_configured: boolean;
}

export interface SystemStatus {
  application_mode: string;
  authentication_required: boolean;
  supabase_configured: boolean;
  publish_mode: PublishMode;
  automation_enabled: boolean;
  publishing_enabled: boolean;
  timezone: string;
  graph_api_version: string;
  facebook: FacebookConfigurationStatus;
}

export interface SystemSnapshot {
  health: HealthStatus;
  status: SystemStatus;
  facebook: FacebookConnectionStatus;
}
