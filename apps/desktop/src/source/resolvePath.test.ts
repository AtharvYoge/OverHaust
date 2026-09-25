import { describe, expect, it } from "vitest";
import { resolveSourcePath } from "./resolvePath";

const PROJECT_ROOT = "/Volumes/Atharv Work/LabKOT/restaurant_pos";

describe("resolveSourcePath", () => {
  it("resolves a valid repo-relative path under the project root", () => {
    const result = resolveSourcePath(PROJECT_ROOT, {
      repoRelativeFile: "lib/services/order_service.dart",
      line: 217,
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.repoRelativeDisplay).toBe("lib/services/order_service.dart");
      expect(result.resolvedPath).toBe(
        "/Volumes/Atharv Work/LabKOT/restaurant_pos/lib/services/order_service.dart",
      );
    }
  });

  it("rejects path traversal that escapes the repository root", () => {
    const result = resolveSourcePath(PROJECT_ROOT, {
      repoRelativeFile: "../../etc/passwd",
    });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toContain("escapes");
    }
  });

  it("rejects missing or empty file paths", () => {
    expect(
      resolveSourcePath(PROJECT_ROOT, {
        repoRelativeFile: "",
      }).ok,
    ).toBe(false);

    expect(
      resolveSourcePath(PROJECT_ROOT, {
        repoRelativeFile: "   ",
      }).ok,
    ).toBe(false);
  });

  it("rejects absolute paths outside the project root", () => {
    const result = resolveSourcePath(PROJECT_ROOT, {
      absoluteFile: "/etc/passwd",
    });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toContain("outside");
    }
  });

  it("accepts absolute paths inside the project root", () => {
    const absolute = `${PROJECT_ROOT}/lib/services/order_service.dart`;
    const result = resolveSourcePath(PROJECT_ROOT, {
      absoluteFile: absolute,
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.repoRelativeDisplay).toBe("lib/services/order_service.dart");
    }
  });

  it("rejects when project root is unavailable", () => {
    const result = resolveSourcePath(null, {
      repoRelativeFile: "lib/main.dart",
    });

    expect(result.ok).toBe(false);
  });
});
