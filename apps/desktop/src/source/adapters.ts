import type { AnswerSourceRef } from "../answer/types";
import type { CodeFlowStep } from "../types/codeFlow";
import type { SearchResult } from "../types/search";
import type { SourceLocation } from "./types";

function toLocation(file: string, line?: number): SourceLocation | null {
  const trimmed = file.trim();
  if (!trimmed) {
    return null;
  }
  return {
    file: trimmed,
    ...(line && line > 0 ? { line } : {}),
  };
}

export function sourceLocationFromSearchResult(result: SearchResult): SourceLocation | null {
  const meta = result.metadata ?? {};
  const filePath = meta.file_path ?? meta.source_ref;
  if (typeof filePath !== "string" || !filePath.trim()) {
    return null;
  }
  const line = typeof meta.symbol_line === "number" ? meta.symbol_line : undefined;
  return toLocation(filePath, line);
}

export function sourceLocationFromCodeFlowStep(step: CodeFlowStep): SourceLocation | null {
  return toLocation(step.file, step.line);
}

export function sourceLocationFromAnswerSource(source: AnswerSourceRef): SourceLocation | null {
  return toLocation(source.file, source.line);
}
