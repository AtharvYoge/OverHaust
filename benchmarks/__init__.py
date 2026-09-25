"""
OverHaust context-efficiency benchmark harness.

Isolated from production retrieval/context paths.
Calls invoke_context_request() for the OverHaust condition only —
never modifies how that function behaves.
"""

BENCHMARK_VERSION = "0.3.0"
