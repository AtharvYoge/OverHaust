import { invoke } from "@tauri-apps/api/core";
import type { SourceAvailability, SourceLocation, SourceOpenResult } from "./types";
import { sourceLocationToPathInput } from "./resolvePath";

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function checkSourceAvailability(
  projectRoot: string | null,
  location: SourceLocation,
): Promise<SourceAvailability> {
  if (!projectRoot?.trim()) {
    return {
      available: false,
      displayPath: location.file,
      reason: "Project root is unavailable.",
    };
  }

  if (!isTauriRuntime()) {
    return {
      available: false,
      displayPath: location.file,
      reason: "Source navigation requires the desktop app.",
    };
  }

  try {
    const result = await invoke<SourceAvailability>("check_source_availability", {
      projectRoot: projectRoot.trim(),
      file: location.file.trim(),
      line: location.line ?? null,
    });
    return result;
  } catch {
    return {
      available: false,
      displayPath: location.file,
      reason: "Source unavailable",
    };
  }
}

export async function openSourceInDefaultApp(
  projectRoot: string | null,
  location: SourceLocation,
): Promise<SourceOpenResult> {
  if (!projectRoot?.trim()) {
    return { ok: false, reason: "Project root is unavailable." };
  }

  if (!isTauriRuntime()) {
    return { ok: false, reason: "Source navigation requires the desktop app." };
  }

  const input = sourceLocationToPathInput(location);
  if (!input.repoRelativeFile && !input.absoluteFile) {
    return { ok: false, reason: "Source file path is missing." };
  }

  try {
    const result = await invoke<{ opened: boolean; line_navigation_applied: boolean }>(
      "open_source_file",
      {
        projectRoot: projectRoot.trim(),
        file: location.file.trim(),
        line: location.line ?? null,
      },
    );

    if (!result.opened) {
      return { ok: false, reason: "Couldn't open this source file." };
    }

    return {
      ok: true,
      lineNavigationApplied: result.line_navigation_applied,
    };
  } catch {
    return { ok: false, reason: "Couldn't open this source file." };
  }
}
