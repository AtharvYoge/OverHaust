/** Local OverHaust API configuration for the desktop shell. */
export const BACKEND_BASE_URL = "http://localhost:8000";

export const BACKEND_HEALTH_PATH = "/health";

export const BACKEND_HEALTH_URL = `${BACKEND_BASE_URL}${BACKEND_HEALTH_PATH}`;

/** Short label shown in the connected state. */
export const BACKEND_HOST_LABEL = "localhost:8000";

/** Abort health checks that hang (backend not running, network stall). */
export const BACKEND_HEALTH_TIMEOUT_MS = 5_000;
