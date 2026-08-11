import type { FacebookConnectionStatus } from "../types/facebook";
import { apiRequest } from "./client";

export function getFacebookConnectionStatus(): Promise<FacebookConnectionStatus> {
  return apiRequest<FacebookConnectionStatus>("/api/facebook/status");
}

export function testFacebookConnection(): Promise<FacebookConnectionStatus> {
  return apiRequest<FacebookConnectionStatus>("/api/facebook/test-connection", {
    method: "POST",
  });
}
