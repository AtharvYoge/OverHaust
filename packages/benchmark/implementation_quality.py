"""
Deterministic implementation quality checks for Phase 15 write-task benchmark.

Evaluates git diffs and source patterns without LLM subjective scoring.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


PRINTING_PREFIXES = (
    "lib/services/printing/",
    "lib/models/printing/",
    "lib/models/configuration/",
    "test/kitchen_print",
    "test/print_",
)

CORE_FILES = {
    "lib/services/printing/kitchen_print_router.dart",
    "lib/services/printing/kitchen_print_service.dart",
}


@dataclass
class QualityReport:
    repo_path: str
    baseline_sha: Optional[str] = None
    changed_files: List[str] = field(default_factory=list)
    unrelated_changes: List[str] = field(default_factory=list)
    tests_changed: List[str] = field(default_factory=list)
    has_multiple_printer_support: bool = False
    has_routing_logic: bool = False
    single_printer_patterns_present: bool = False
    architecture_patterns: List[str] = field(default_factory=list)
    compile_analyze_ok: Optional[bool] = None
    compile_analyze_output: str = ""
    tests_passed: Optional[bool] = None
    tests_output: str = ""
    tests_ran: List[str] = field(default_factory=list)
    agent_completed: bool = False
    correct_implementation: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "baseline_sha": self.baseline_sha,
            "changed_files": self.changed_files,
            "unrelated_changes": self.unrelated_changes,
            "tests_changed": self.tests_changed,
            "has_multiple_printer_support": self.has_multiple_printer_support,
            "has_routing_logic": self.has_routing_logic,
            "single_printer_patterns_present": self.single_printer_patterns_present,
            "architecture_patterns": self.architecture_patterns,
            "compile_analyze_ok": self.compile_analyze_ok,
            "compile_analyze_output": self.compile_analyze_output[:2000],
            "tests_passed": self.tests_passed,
            "tests_output": self.tests_output[:4000],
            "tests_ran": self.tests_ran,
            "agent_completed": self.agent_completed,
            "correct_implementation": self.correct_implementation,
            "notes": self.notes,
        }


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )


def _changed_files(repo: Path) -> List[str]:
    proc = _git(repo, "diff", "--name-only", "HEAD")
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _is_unrelated(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if any(normalized.startswith(p) for p in PRINTING_PREFIXES):
        return False
    if normalized.startswith("test/") and ("print" in normalized or "kitchen" in normalized):
        return False
    return True


def _read_repo_text(repo: Path, rel_paths: Set[str]) -> str:
    parts: List[str] = []
    for rel in rel_paths:
        full = repo / rel
        if full.exists():
            try:
                parts.append(full.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    diff = _git(repo, "diff", "HEAD")
    if diff.stdout:
        parts.append(diff.stdout)
    return "\n".join(parts)


def _scan_implementation_signals(repo: Path, changed: List[str]) -> Dict[str, Any]:
    scan_paths = set(changed) | CORE_FILES
    text = _read_repo_text(repo, {p for p in scan_paths if (repo / p).exists()})

    signals = {
        "has_multiple_printer_support": bool(
            re.search(r"kitchenPrinters", text)
            and re.search(r"SavedPrinter", text)
            and (
                len(re.findall(r"PrinterRole\.kitchen", text)) >= 2
                or "categoryIds" in text
            )
        ),
        "has_routing_logic": bool(
            re.search(r"KitchenPrintRouter", text)
            and (
                re.search(r"enqueueRoutedJobsForOrder", text)
                or re.search(r"_resolvePrinterRoutes", text)
                or re.search(r"resolve\s*\(", text)
            )
        ),
        "single_printer_patterns_present": bool(
            re.search(r"defaultIdFor\(PrinterRole\.kitchen\)", text)
            or re.search(r"enqueueForOrder", text)
        ),
        "architecture_patterns": [],
    }
    for pattern, label in [
        (r"class KitchenPrintRouter", "KitchenPrintRouter"),
        (r"class KitchenPrintService", "KitchenPrintService"),
        (r"KitchenPrintRoute", "KitchenPrintRoute"),
        (r"PrinterPreferences", "PrinterPreferences"),
        (r"enqueueRoutedJobsForOrder", "enqueueRoutedJobsForOrder"),
    ]:
        if re.search(pattern, text):
            signals["architecture_patterns"].append(label)
    return signals


def _run_dart_analyze(repo: Path, paths: List[str]) -> tuple[Optional[bool], str]:
    if not paths:
        return None, "no changed files to analyze"
    flutter = _find_flutter(repo)
    if not flutter:
        return None, "flutter not found"
    targets = [str(repo / p) for p in paths if (repo / p).exists()]
    if not targets:
        return None, "no analyze targets"
    proc = subprocess.run(
        [flutter, "analyze", *targets],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=300,
    )
    ok = proc.returncode == 0
    output = (proc.stdout + proc.stderr).strip()
    return ok, output


def _run_kitchen_tests(repo: Path) -> tuple[Optional[bool], str, List[str]]:
    flutter = _find_flutter(repo)
    test_file = repo / "test" / "kitchen_print_service_test.dart"
    tests = [str(test_file)] if test_file.exists() else []
    if not flutter or not tests:
        return None, "flutter or kitchen_print_service_test.dart unavailable", tests
    proc = subprocess.run(
        [flutter, "test", *tests],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=600,
    )
    output = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, output, tests


def _find_flutter(repo: Path) -> Optional[str]:
    import shutil

    if shutil.which("flutter"):
        return "flutter"
    candidate = repo.parent.parent / "flutter" / "bin" / "flutter"
    if candidate.exists():
        return str(candidate)
    return None


def evaluate_repo(
    repo_path: str | Path,
    *,
    baseline_sha: Optional[str] = None,
    agent_completed: bool = False,
) -> QualityReport:
    repo = Path(repo_path)
    report = QualityReport(
        repo_path=str(repo),
        baseline_sha=baseline_sha,
        agent_completed=agent_completed,
    )

    if not repo.exists():
        report.notes.append("repository path does not exist")
        return report

    sha_proc = _git(repo, "rev-parse", "HEAD")
    if sha_proc.returncode == 0:
        report.baseline_sha = report.baseline_sha or sha_proc.stdout.strip()

    changed = _changed_files(repo)
    report.changed_files = changed
    report.unrelated_changes = [p for p in changed if _is_unrelated(p)]
    report.tests_changed = [p for p in changed if p.startswith("test/")]

    signals = _scan_implementation_signals(repo, changed)
    report.has_multiple_printer_support = signals["has_multiple_printer_support"]
    report.has_routing_logic = signals["has_routing_logic"]
    report.single_printer_patterns_present = signals["single_printer_patterns_present"]
    report.architecture_patterns = signals["architecture_patterns"]

    analyze_paths = changed or list(CORE_FILES)
    report.compile_analyze_ok, report.compile_analyze_output = _run_dart_analyze(
        repo, analyze_paths,
    )
    report.tests_passed, report.tests_output, report.tests_ran = _run_kitchen_tests(repo)

    if not changed:
        report.notes.append(
            "No git diff — feature may already exist at baseline; evaluating existing code."
        )

    report.correct_implementation = (
        report.has_multiple_printer_support
        and report.has_routing_logic
        and report.single_printer_patterns_present
        and not report.unrelated_changes
        and report.tests_passed is not False
    )

    if report.tests_passed is False:
        report.notes.append("kitchen_print_service_test.dart did not pass")
    if report.unrelated_changes:
        report.notes.append(f"Unrelated files modified: {report.unrelated_changes}")

    return report
