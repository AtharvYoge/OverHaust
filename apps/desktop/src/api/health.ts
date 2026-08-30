import {
  BACKEND_HEALTH_TIMEOUT_MS,
  BACKEND_HEALTH_URL,
} from "../config/backend";

interface HealthResponse {
  status?: string;
}

function isHealthyPayload(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const status = (value as HealthResponse).status;
  return typeof status === "string" && status.toLowerCase() === "healthy";
}

/**
 * Returns true when the local OverHaust API responds with a healthy status.
 * Never throws — callers treat false as unavailable.
 */
export async function checkBackendHealth(): Promise<boolean> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    BACKEND_HEALTH_TIMEOUT_MS,
  );

  try {
    const response = await fetch(BACKEND_HEALTH_URL, {
      method: "GET",
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      return false;
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      return false;
    }

    return isHealthyPayload(payload);
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeoutId);
  }
}
