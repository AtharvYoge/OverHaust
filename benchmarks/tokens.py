"""
Token counting for the benchmark harness.

Wraps packages.tokenization.TokenEstimator (tiktoken) and always labels
counts as estimated_token_count unless an exact provider count is supplied.

Never silently promotes an estimate to an exact count.
Never derives "savings" from character length alone.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from benchmarks.schemas import MeasurementSource, TokenKind, TokenMeasurement


class TokenCounter:
    """
    Benchmark-facing token counter.

    tiktoken (via TokenEstimator) yields ESTIMATED counts for OpenAI-family
    encodings. Exact counts require external provider telemetry passed in
    via record_exact().
    """

    def __init__(self, model: Optional[str] = None, *, prefer_tiktoken: bool = True):
        self.model = model
        self.prefer_tiktoken = prefer_tiktoken
        self._estimator = None
        self._tiktoken_available: Optional[bool] = None

    def _get_estimator(self):
        if self._estimator is None:
            from packages.tokenization.token_estimator import TokenEstimator
            self._estimator = TokenEstimator(default_model=self.model)
        return self._estimator

    def _tiktoken_ok(self) -> bool:
        if self._tiktoken_available is not None:
            return self._tiktoken_available
        try:
            self._get_estimator().estimate_tokens("ok")
            self._tiktoken_available = True
        except Exception:
            self._tiktoken_available = False
        return self._tiktoken_available

    def count_text(self, text: str, *, model: Optional[str] = None) -> TokenMeasurement:
        if text is None:
            return TokenMeasurement.unavailable("text is None")
        if self.prefer_tiktoken and self._tiktoken_ok():
            value = self._get_estimator().estimate_tokens(text, model=model or self.model)
            return TokenMeasurement.estimated(
                value,
                source=MeasurementSource.ESTIMATED,
                note=f"tiktoken via TokenEstimator (model={model or self.model or 'default'})",
            )
        # Explicit fallback — labelled, never pretended to be exact.
        approx = max(1, (len(text) + 3) // 4) if text else 0
        return TokenMeasurement.estimated(
            approx,
            source=MeasurementSource.ESTIMATED,
            note="FALLBACK char/4 estimator; tiktoken unavailable. NOT an exact count.",
        )

    def count_messages(self, messages: Sequence[Dict[str, Any]], *,
                       model: Optional[str] = None) -> TokenMeasurement:
        if not messages:
            return TokenMeasurement.estimated(0, note="empty messages")
        if self.prefer_tiktoken and self._tiktoken_ok():
            # TokenEstimator.estimate_messages_tokens expects string values.
            cleaned: List[Dict[str, str]] = []
            for msg in messages:
                cleaned.append({
                    k: (v if isinstance(v, str) else str(v))
                    for k, v in msg.items()
                })
            value = self._get_estimator().estimate_messages_tokens(
                cleaned, model=model or self.model
            )
            return TokenMeasurement.estimated(
                value,
                note=f"tiktoken messages estimate (model={model or self.model or 'default'})",
            )
        joined = "\n".join(str(m.get("content", "")) for m in messages)
        return self.count_text(joined, model=model)

    def count_file_content(self, content: str, *, path: str = "") -> TokenMeasurement:
        m = self.count_text(content)
        if path:
            m.note = (m.note + f"; file={path}").strip("; ")
        return m

    def count_context(self, context_text: str) -> TokenMeasurement:
        m = self.count_text(context_text)
        m.note = (m.note + "; field=overhaust_or_baseline_context").strip("; ")
        return m

    @staticmethod
    def record_exact(value: int, *, note: str = "provider telemetry") -> TokenMeasurement:
        """Only path that may produce exact_token_count."""
        return TokenMeasurement.exact(int(value), note=note)

    @staticmethod
    def classify(measurement: TokenMeasurement) -> str:
        return measurement.kind.value


def assert_kinds_not_mixed(measurements: Sequence[TokenMeasurement]) -> None:
    """Raise if callers try to treat exact and estimated as interchangeable."""
    kinds = {m.kind for m in measurements if m.value is not None}
    if TokenKind.EXACT in kinds and TokenKind.ESTIMATED in kinds:
        raise ValueError(
            "Refusing to mix exact_token_count and estimated_token_count "
            "in a single comparison. Compare within one kind only."
        )
