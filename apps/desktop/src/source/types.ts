/** A source reference within a project repository. */
export type SourceLocation = {
  file: string;
  line?: number;
  column?: number;
};

/** Input for path resolution — distinguishes repo-relative vs absolute paths. */
export type SourcePathInput = {
  /** Repo-relative path from backend evidence, e.g. lib/services/order_service.dart */
  repoRelativeFile?: string;
  /** Absolute path when backend already provides one under project root */
  absoluteFile?: string;
  line?: number;
  column?: number;
};

export type SourcePathResolution =
  | {
      ok: true;
      repoRelativeDisplay: string;
      resolvedPath: string;
    }
  | {
      ok: false;
      reason: string;
    };

export type SourceAvailability = {
  available: boolean;
  displayPath: string;
  reason?: string;
};

export type SourceOpenResult =
  | {
      ok: true;
      lineNavigationApplied: boolean;
    }
  | {
      ok: false;
      reason: string;
    };
