"""
Deterministic correctness against AnswerRubric (defined before results).

No LLM judge. Token reduction is only meaningful alongside these scores.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from benchmarks.schemas import AnswerRubric, BenchmarkTask, CorrectnessResult


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in (haystack or "").lower()


def _found_missing(haystack: str, items: Sequence[str]) -> tuple[List[str], List[str]]:
    found, missing = [], []
    for item in items:
        if not item:
            continue
        if _contains(haystack, item):
            found.append(item)
        else:
            missing.append(item)
    return found, missing


def evaluate_rubric(rubric: AnswerRubric, answer_text: Optional[str]) -> CorrectnessResult:
    text = answer_text or ""
    if not text.strip():
        return CorrectnessResult(
            correct=None,
            notes="No answer_text; correctness not measured.",
        )

    def fact_found(fact: str) -> bool:
        # Prefer explicit FOUND markers from the sim agent / careful authors.
        if f"FOUND: {fact}" in text or f"FOUND symbol: {fact}" in text or f"FOUND file: {fact}" in text:
            return True
        # Fallback: fact appears and is not only on a MISSING line.
        if not _contains(text, fact):
            return False
        for line in text.splitlines():
            if fact.lower() in line.lower() and "MISSING" in line.upper():
                continue
            if fact.lower() in line.lower():
                return True
        return False

    facts_found, facts_missing = [], []
    for fact in rubric.required_facts:
        if not fact:
            continue
        if fact_found(fact):
            facts_found.append(fact)
        else:
            facts_missing.append(fact)

    files_found, files_missing = [], []
    for path in rubric.required_files:
        if fact_found(path) or (_contains(text, path) and f"MISSING file: {path}" not in text):
            files_found.append(path)
        else:
            files_missing.append(path)

    symbols_found, symbols_missing = [], []
    for sym in rubric.required_symbols:
        if fact_found(sym) or (
            _contains(text, sym) and f"MISSING symbol: {sym}" not in text
        ):
            symbols_found.append(sym)
        else:
            symbols_missing.append(sym)

    any_failures: List[str] = []
    for group in rubric.required_any_of:
        if group and not any(_contains(text, g) for g in group):
            any_failures.append("|".join(group))

    forbidden_hit = [f for f in rubric.forbidden_claims if _contains(text, f)]

    checks = 0
    hits = 0
    for found, missing in (
        (facts_found, facts_missing),
        (files_found, files_missing),
        (symbols_found, symbols_missing),
    ):
        total = len(found) + len(missing)
        if total:
            checks += total
            hits += len(found)
    for group in rubric.required_any_of:
        if group:
            checks += 1
            if any(_contains(text, g) for g in group):
                hits += 1
    if rubric.forbidden_claims:
        checks += len(rubric.forbidden_claims)
        hits += len(rubric.forbidden_claims) - len(forbidden_hit)

    evidence_score = round(hits / checks, 4) if checks else None
    correct = (
        len(facts_missing) == 0
        and not any_failures
        and not forbidden_hit
    )
    notes = "Deterministic rubric check (no LLM judge)."
    if any_failures:
        notes += f" Missing any-of groups: {any_failures}."
    if forbidden_hit:
        notes += f" Forbidden claims present: {forbidden_hit}."

    return CorrectnessResult(
        correct=correct,
        required_facts_found=facts_found,
        required_facts_missing=facts_missing + [f"[any_of]{g}" for g in any_failures],
        expected_files_found=files_found,
        expected_files_missing=files_missing,
        expected_symbols_found=symbols_found,
        expected_symbols_missing=symbols_missing,
        evidence_score=evidence_score,
        notes=notes,
    )


def evaluate_answer(
    task: BenchmarkTask,
    answer_text: Optional[str],
    *,
    context_text: Optional[str] = None,
) -> CorrectnessResult:
    """
    Score an answer against the task rubric.

    If answer_text is empty but context_text is provided, evidence may still
    be scored from context (correctness remains None).
    """
    rubric = task.get_rubric()
    if answer_text and answer_text.strip():
        return evaluate_rubric(rubric, answer_text)

    if context_text and context_text.strip():
        # Evidence-only pass against context (not a correctness claim).
        proxy = evaluate_rubric(rubric, context_text)
        return CorrectnessResult(
            correct=None,
            required_facts_found=proxy.required_facts_found,
            required_facts_missing=proxy.required_facts_missing,
            expected_files_found=proxy.expected_files_found,
            expected_files_missing=proxy.expected_files_missing,
            expected_symbols_found=proxy.expected_symbols_found,
            expected_symbols_missing=proxy.expected_symbols_missing,
            evidence_score=proxy.evidence_score,
            notes="Scored context/evidence only; no answer_text for correctness.",
        )

    return CorrectnessResult(
        correct=None,
        notes="No answer_text provided; correctness not measured.",
    )


def evaluate_batch(
    task: BenchmarkTask,
    answers: Iterable[Optional[str]],
) -> List[CorrectnessResult]:
    return [evaluate_answer(task, a) for a in answers]
