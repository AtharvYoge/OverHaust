import { useCallback, useEffect, useRef, useState } from "react";
import { checkBackendHealth } from "../api/health";

export type BackendHealthStatus = "connecting" | "connected" | "disconnected";

export interface BackendHealthState {
  status: BackendHealthStatus;
  retry: () => void;
}

export function useBackendHealth(): BackendHealthState {
  const [status, setStatus] = useState<BackendHealthStatus>("connecting");
  const activeRequest = useRef(0);

  const runCheck = useCallback(async () => {
    const requestId = activeRequest.current + 1;
    activeRequest.current = requestId;
    setStatus("connecting");

    const healthy = await checkBackendHealth();

    if (activeRequest.current !== requestId) {
      return;
    }

    setStatus(healthy ? "connected" : "disconnected");
  }, []);

  useEffect(() => {
    void runCheck();
  }, [runCheck]);

  const retry = useCallback(() => {
    void runCheck();
  }, [runCheck]);

  return { status, retry };
}
