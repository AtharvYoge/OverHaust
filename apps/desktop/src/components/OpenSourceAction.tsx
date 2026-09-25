import { useCallback, useEffect, useState } from "react";
import type { SourceLocation } from "../source/types";
import { useSourceNavigation } from "../source/useSourceNavigation";
import "./OpenSourceAction.css";

interface OpenSourceActionProps {
  location: SourceLocation | null;
  className?: string;
  compact?: boolean;
}

type ActionState = "checking" | "ready" | "opening" | "error";

export function OpenSourceAction({ location, className, compact = false }: OpenSourceActionProps) {
  const { projectRoot, navigation } = useSourceNavigation();
  const [state, setState] = useState<ActionState>("checking");
  const [available, setAvailable] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const checkAvailability = useCallback(async () => {
    if (!location?.file.trim()) {
      setAvailable(false);
      setState("ready");
      return;
    }

    setState("checking");
    const result = await navigation.checkAvailability(projectRoot, location);
    setAvailable(result.available);
    setState("ready");
  }, [location, navigation, projectRoot]);

  useEffect(() => {
    void checkAvailability();
  }, [checkAvailability]);

  const handleOpen = useCallback(async () => {
    if (!location?.file.trim() || !available) {
      return;
    }

    setState("opening");
    setErrorMessage(null);

    const result = await navigation.openDefaultApp(projectRoot, location);
    if (result.ok) {
      setState("ready");
      return;
    }

    setErrorMessage(result.reason);
    setState("error");
  }, [available, location, navigation, projectRoot]);

  const disabled =
    !location?.file.trim() ||
    !projectRoot ||
    !available ||
    state === "checking" ||
    state === "opening";

  const title = disabled && !errorMessage ? "Source unavailable" : undefined;

  return (
    <span
      className={[
        "open-source-action",
        compact ? "open-source-action--compact" : "",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <button
        type="button"
        className={[
          "open-source-action__button",
          state === "opening" ? "open-source-action__button--loading" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={() => void handleOpen()}
        disabled={disabled}
        title={title}
        aria-busy={state === "opening"}
      >
        {state === "opening" ? "Opening…" : "Open source"}
      </button>
      {state === "error" && errorMessage ? (
        <span className="open-source-action__error">
          {errorMessage}{" "}
          <button
            type="button"
            className="open-source-action__retry"
            onClick={() => void handleOpen()}
          >
            Retry
          </button>
        </span>
      ) : null}
    </span>
  );
}
