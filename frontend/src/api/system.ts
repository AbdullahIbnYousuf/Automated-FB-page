import type { HealthStatus, SystemSnapshot, SystemStatus } from "../types/system";
import { apiRequest } from "./client";
import { getFacebookConnectionStatus } from "./facebook";

export async function loadSystemSnapshot(): Promise<SystemSnapshot> {
  const [health, status, facebook] = await Promise.all([
    apiRequest<HealthStatus>("/api/health"),
    apiRequest<SystemStatus>("/api/system/status"),
    getFacebookConnectionStatus(),
  ]);

  return { health, status, facebook };
}
