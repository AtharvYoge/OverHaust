import type { SourcePathInput, SourcePathResolution } from "./types";

function normalizeSeparators(path: string): string {
  return path.replace(/\\/g, "/");
}

function hasNullByte(path: string): boolean {
  return path.includes("\0");
}

function isWindowsDrivePath(path: string): boolean {
  return /^[a-zA-Z]:/.test(path);
}

function isAbsolutePath(path: string): boolean {
  const normalized = normalizeSeparators(path);
  return normalized.startsWith("/") || isWindowsDrivePath(normalized);
}

function splitPathSegments(path: string): string[] {
  return normalizeSeparators(path)
    .split("/")
    .filter((segment) => segment.length > 0 && segment !== ".");
}

function normalizeProjectRoot(projectRoot: string): string {
  const trimmed = projectRoot.trim();
  const normalized = normalizeSeparators(trimmed).replace(/\/+$/, "");
  return normalized || trimmed;
}

function joinUnderRoot(projectRoot: string, relativeFile: string): string | null {
  const root = normalizeProjectRoot(projectRoot);
  const segments = splitPathSegments(relativeFile);
  const stack: string[] = [];

  for (const segment of segments) {
    if (segment === "..") {
      if (stack.length === 0) {
        return null;
      }
      stack.pop();
      continue;
    }
    stack.push(segment);
  }

  if (stack.length === 0) {
    return null;
  }

  return `${root}/${stack.join("/")}`;
}

function isPathUnderRoot(projectRoot: string, absolutePath: string): boolean {
  const root = normalizeProjectRoot(projectRoot);
  const candidate = normalizeSeparators(absolutePath).replace(/\/+$/, "");
  return candidate === root || candidate.startsWith(`${root}/`);
}

export function resolveSourcePath(
  projectRoot: string | null | undefined,
  input: SourcePathInput,
): SourcePathResolution {
  const root = projectRoot?.trim();
  if (!root) {
    return { ok: false, reason: "Project root is unavailable." };
  }

  const fileCandidate = input.absoluteFile?.trim() || input.repoRelativeFile?.trim();
  if (!fileCandidate) {
    return { ok: false, reason: "Source file path is missing." };
  }

  if (hasNullByte(fileCandidate) || hasNullByte(root)) {
    return { ok: false, reason: "Source file path is invalid." };
  }

  if (isAbsolutePath(fileCandidate)) {
    const normalized = normalizeSeparators(fileCandidate);
    if (!isPathUnderRoot(root, normalized)) {
      return { ok: false, reason: "Source file is outside the project root." };
    }
    const display = normalized.slice(normalizeProjectRoot(root).length + 1) || normalized;
    return {
      ok: true,
      repoRelativeDisplay: display,
      resolvedPath: normalized,
    };
  }

  const resolved = joinUnderRoot(root, fileCandidate);
  if (!resolved) {
    return { ok: false, reason: "Source file path escapes the project root." };
  }

  return {
    ok: true,
    repoRelativeDisplay: normalizeSeparators(fileCandidate).replace(/^\/+/, ""),
    resolvedPath: resolved,
  };
}

export function sourceLocationToPathInput(location: {
  file: string;
  line?: number;
  column?: number;
}): SourcePathInput {
  const file = location.file.trim();
  if (isAbsolutePath(file)) {
    return {
      absoluteFile: file,
      line: location.line,
      column: location.column,
    };
  }
  return {
    repoRelativeFile: file,
    line: location.line,
    column: location.column,
  };
}
