import { checkSourceAvailability, openSourceInDefaultApp } from "./openDefaultApp";
import type { SourceAvailability, SourceLocation, SourceOpenResult } from "./types";

export interface SourceNavigationService {
  checkAvailability(
    projectRoot: string | null,
    location: SourceLocation,
  ): Promise<SourceAvailability>;
  openDefaultApp(projectRoot: string | null, location: SourceLocation): Promise<SourceOpenResult>;
  // Future: openInVSCode, openInCursor, openInZed
}

export const sourceNavigation: SourceNavigationService = {
  checkAvailability: checkSourceAvailability,
  openDefaultApp: openSourceInDefaultApp,
};
