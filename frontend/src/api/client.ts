import { supabase } from "../auth/supabase";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

interface ErrorPayload {
  error?: {
    code?: string;
    message?: string;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const accessToken = await getAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...init?.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      await supabase?.auth.signOut({ scope: "local" });
    }
    let payload: ErrorPayload | null = null;
    try {
      payload = (await response.json()) as ErrorPayload;
    } catch {
      payload = null;
    }
    throw new ApiError(
      payload?.error?.message ?? "The backend could not complete this request.",
      payload?.error?.code ?? "REQUEST_FAILED",
      response.status,
    );
  }

  return (await response.json()) as T;
}

export async function apiBlobRequest(path: string): Promise<Blob> {
  const accessToken = await getAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    headers: {
      Accept: "image/jpeg,image/png",
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    if (response.status === 401) {
      await supabase?.auth.signOut({ scope: "local" });
    }
    throw new ApiError(
      "The image could not be loaded.",
      "MEDIA_UNAVAILABLE",
      response.status,
    );
  }
  return response.blob();
}

async function getAccessToken(): Promise<string> {
  if (!supabase) {
    throw new ApiError(
      "Authentication is not configured.",
      "AUTH_CONFIGURATION",
      503,
    );
  }
  const { data, error } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;
  if (error || !accessToken) {
    throw new ApiError("Sign in to continue.", "AUTH_REQUIRED", 401);
  }
  return accessToken;
}
