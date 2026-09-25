import { useMemo } from "react";
import { useActiveProject } from "../context/ActiveProjectContext";
import { sourceNavigation, type SourceNavigationService } from "./navigation";

export function useSourceNavigation(): {
  projectRoot: string | null;
  navigation: SourceNavigationService;
} {
  const { activeProject } = useActiveProject();

  const projectRoot = activeProject?.root_path?.trim() || null;

  return useMemo(
    () => ({
      projectRoot,
      navigation: sourceNavigation,
    }),
    [projectRoot],
  );
}
