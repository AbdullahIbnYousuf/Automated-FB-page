export type FacebookConnectionState =
  | "not_configured"
  | "not_verified"
  | "connected"
  | "invalid_configuration"
  | "invalid_credentials"
  | "expired_credentials"
  | "page_inaccessible"
  | "page_mismatch"
  | "insufficient_access"
  | "meta_unavailable"
  | "malformed_response"
  | "error";

export interface FacebookPageIdentity {
  id: string;
  name: string;
}

export interface FacebookConnectionStatus {
  connected: boolean;
  status: FacebookConnectionState;
  page_id_configured: boolean;
  access_token_configured: boolean;
  page: FacebookPageIdentity | null;
  api_version: string;
  message: string;
  last_checked_at: string | null;
  publishing_capability_verified: boolean;
}
