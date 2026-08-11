import type { HealthStatus, SystemSnapshot, SystemStatus } from "../types/system";
import { apiRequest } from "./client";

export async function loadSystemSnapshot(): Promise<SystemSnapshot> {
  const [health, status] = await Promise.all([
    apiRequest<HealthStatus>("/api/health"),
    apiRequest<SystemStatus>("/api/system/status"),
  ]);

  return { health, status };
}
