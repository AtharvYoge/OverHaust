import { BACKEND_HOST_LABEL } from "../config/backend";
import type { BackendHealthStatus } from "../hooks/useBackendHealth";
import { Button } from "./ui/Button";
import "./BackendStatus.css";

interface BackendStatusProps {
  status: BackendHealthStatus;
  onRetry: () => void;
  compact?: boolean;
}

export function BackendStatus({ status, onRetry, compact = false }: BackendStatusProps) {
  return (
    <div
      className={`backend-status backend-status--${status}${compact ? " backend-status--compact" : ""}`}
      role="status"
      aria-live="polite"
    >
      <span className="backend-status__indicator" aria-hidden="true" />
      <div className="backend-status__text">
        {status === "connecting" ? (
          <span className="backend-status__label">Connecting to OverHaust…</span>
        ) : null}
        {status === "connected" ? (
          <>
            <span className="backend-status__label">Backend connected</span>
            {!compact ? (
              <span className="backend-status__host">{BACKEND_HOST_LABEL}</span>
            ) : null}
          </>
        ) : null}
        {status === "disconnected" ? (
          <>
            <span className="backend-status__label">Backend unavailable</span>
            <Button
              variant="ghost"
              size="sm"
              className="backend-status__retry"
              onClick={onRetry}
            >
              Retry
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}
