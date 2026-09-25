"""Tests for compact agent context assembly."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from packages.context.agent_context import (
    MAX_PROMPT_LENGTH,
    MCP_MAX_PROMPT_LENGTH,
    assemble_agent_context,
    invoke_context_request,
    is_call_delegation_question,
    list_projects_for_agent,
    resolve_project_id,
    should_include_code_flow,
)
from packages.knowledge.abstention import RELEVANCE_SUFFICIENT
from packages.memory.memory_store import MemoryStore
from packages.retrieval.test_index_retrieval import make_kot_tree
from packages.shared.config import get_context_max_files, get_context_max_symbols


@pytest.fixture
def temp_store():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    store = MemoryStore(tmp.name)
    yield store
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)


def test_should_include_code_flow_auto():
    assert should_include_code_flow(
        "How does a food order reach the kitchen?",
        "auto",
        RELEVANCE_SUFFICIENT + 0.1,
    )
    assert not should_include_code_flow(
        "Add support for multiple kitchen printers",
        "auto",
        RELEVANCE_SUFFICIENT + 0.1,
    )
    assert not should_include_code_flow(
        "How does a food order reach the kitchen?",
        False,
        1.0,
    )
    assert should_include_code_flow(
        "Add printer routing",
        True,
        RELEVANCE_SUFFICIENT + 0.1,
    )


def test_assemble_agent_context_abstains_on_unrelated(temp_store):
    temp_store.add_project("abstain-p", "Abstain", "", "")
    result = assemble_agent_context(
        "abstain-p",
        "How does Stripe billing webhook integration work?",
        memory_store=temp_store,
    )
    assert result.insufficient_evidence is True
    assert result.confidence == "insufficient"
    assert result.relevant_files == []
    assert result.relevant_symbols == []
    assert "Stripe" in result.prompt


def test_assemble_agent_context_returns_indexed_symbols(temp_store):
    tmpdir = tempfile.mkdtemp()
    try:
        root = Path(tmpdir)
        make_kot_tree(root)
        temp_store.add_project("ctx-p", "Ctx", "", str(root))
        from services.ingestion.index_store import ProjectIndexStore

        ProjectIndexStore(temp_store).sync_project("ctx-p", str(root))

        result = assemble_agent_context(
            "ctx-p",
            "Where is the KOT generated?",
            memory_store=temp_store,
            include_code_flow=False,
        )
        assert not result.insufficient_evidence
        assert result.relevant_symbols or result.relevant_files
        assert result.context
        assert result.metrics.files_count >= 0
        assert result.metrics.response_bytes > 0
        assert "kot" in result.summary.lower() or "KOT" in result.summary
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_assemble_agent_context_unknown_project(temp_store):
    with pytest.raises(ValueError, match="not found"):
        assemble_agent_context("missing", "anything", memory_store=temp_store)


def test_resolve_project_id(temp_store):
    tmpdir = tempfile.mkdtemp()
    try:
        root = Path(tmpdir)
        make_kot_tree(root)
        temp_store.add_project("resolve-p", "Resolve", "", str(root))
        from services.ingestion.index_store import ProjectIndexStore

        ProjectIndexStore(temp_store).sync_project("resolve-p", str(root))
        assert resolve_project_id(str(root), memory_store=temp_store) == "resolve-p"
        assert resolve_project_id("/nonexistent/path", memory_store=temp_store) is None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_list_projects_for_agent(temp_store):
    temp_store.add_project("listed", "Listed", "desc", "/tmp/listed")
    projects = list_projects_for_agent(memory_store=temp_store)
    assert any(p["project_id"] == "listed" for p in projects)
    listed = next(p for p in projects if p["project_id"] == "listed")
    assert listed["name"] == "Listed"
    assert listed["indexed"] is False
    assert set(listed.keys()) == {
        "project_id", "name", "description", "root_path", "indexed",
    }


def test_invoke_context_request_validates_prompt(temp_store):
    temp_store.add_project("v-p", "V", "", "")
    with pytest.raises(ValueError, match="prompt is required"):
        invoke_context_request("v-p", "   ", memory_store=temp_store)
    with pytest.raises(ValueError, match="maximum length"):
        invoke_context_request("v-p", "x" * (MAX_PROMPT_LENGTH + 1), memory_store=temp_store)


def test_invoke_context_request_mcp_allows_long_prompt(temp_store):
    temp_store.add_project("v-p", "V", "", "")
    long_prompt = "Where is context assembled? " + ("detail " * 80)
    assert len(long_prompt) > MAX_PROMPT_LENGTH
    assert len(long_prompt) < MCP_MAX_PROMPT_LENGTH
    result = invoke_context_request(
        "v-p",
        long_prompt,
        memory_store=temp_store,
        max_prompt_length=MCP_MAX_PROMPT_LENGTH,
    )
    assert result.prompt == long_prompt.strip()
    with pytest.raises(ValueError, match="maximum length"):
        invoke_context_request(
            "v-p",
            "x" * (MCP_MAX_PROMPT_LENGTH + 1),
            memory_store=temp_store,
            max_prompt_length=MCP_MAX_PROMPT_LENGTH,
        )


def test_invoke_context_request_clamps_budgets(temp_store):
    tmpdir = tempfile.mkdtemp()
    try:
        root = Path(tmpdir)
        make_kot_tree(root)
        temp_store.add_project("clamp-p", "Clamp", "", str(root))
        from services.ingestion.index_store import ProjectIndexStore

        ProjectIndexStore(temp_store).sync_project("clamp-p", str(root))

        result = invoke_context_request(
            "clamp-p",
            "Where is the KOT generated?",
            memory_store=temp_store,
            max_files=20,
            max_symbols=30,
        )
        assert len(result.relevant_files) <= get_context_max_files()
        assert len(result.relevant_symbols) <= get_context_max_symbols()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_context_budget_limits(temp_store):
    tmpdir = tempfile.mkdtemp()
    try:
        root = Path(tmpdir)
        make_kot_tree(root)
        temp_store.add_project("budget-p", "Budget", "", str(root))
        from services.ingestion.index_store import ProjectIndexStore

        ProjectIndexStore(temp_store).sync_project("budget-p", str(root))

        result = assemble_agent_context(
            "budget-p",
            "Where is the KOT generated?",
            memory_store=temp_store,
            max_files=2,
            max_symbols=3,
            max_evidence=4,
            include_code_flow=False,
        )
        assert len(result.relevant_files) <= 2
        assert len(result.relevant_symbols) <= 3
        assert len(result.evidence) <= 4
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_selective_flow_on_indexed_project(temp_store):
    tmpdir = tempfile.mkdtemp()
    try:
        root = Path(tmpdir)
        make_kot_tree(root)
        temp_store.add_project("flow-p", "Flow", "", str(root))
        from services.ingestion.index_store import ProjectIndexStore

        ProjectIndexStore(temp_store).sync_project("flow-p", str(root))

        impl = assemble_agent_context(
            "flow-p",
            "Add support for multiple kitchen printers",
            memory_store=temp_store,
            include_code_flow="auto",
        )
        assert impl.metrics.code_flow_included is False

        lookup = assemble_agent_context(
            "flow-p",
            "What does the order service do?",
            memory_store=temp_store,
            include_code_flow="auto",
        )
        assert lookup.metrics.code_flow_included is False

        flow = assemble_agent_context(
            "flow-p",
            "Where does a food order reach the kitchen?",
            memory_store=temp_store,
            include_code_flow="auto",
        )
        assert flow.metrics.code_flow_included is True
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _make_one_hop_tree(root: Path) -> None:
    """Primary method that delegates cross-module, plus noise distractors."""
    (root / "packages" / "agent").mkdir(parents=True)
    (root / "packages" / "context").mkdir(parents=True)
    (root / "packages" / "retrieval").mkdir(parents=True)

    (root / "packages" / "agent" / "autonomous_agent.py").write_text(
        "class OverhaustAgent:\n"
        "    def get_relevant_context(self, project_id, task, root_path=None):\n"
        "        \"\"\"Delegates to invoke_context_request.\"\"\"\n"
        "        from packages.context.agent_context import invoke_context_request\n"
        "\n"
        "        result = invoke_context_request(\n"
        "            project_id,\n"
        "            task,\n"
        "            root_path=root_path,\n"
        "            memory_store=None,\n"
        "        )\n"
        "        self._record_action('get_relevant_context', task, {}, {})\n"
        "        return result.to_dict()\n"
        "\n"
        "    def _record_action(self, action_type, description, parameters, result):\n"
        "        pass\n"
    )
    (root / "packages" / "context" / "agent_context.py").write_text(
        "def invoke_context_request(project_id, prompt, root_path=None, memory_store=None):\n"
        "    \"\"\"Validated entry that assembles agent context.\"\"\"\n"
        "    return assemble_agent_context(\n"
        "        project_id,\n"
        "        prompt,\n"
        "        memory_store=memory_store,\n"
        "    )\n"
        "\n"
        "def assemble_agent_context(project_id, prompt, memory_store=None):\n"
        "    return {'project_id': project_id, 'prompt': prompt}\n"
    )
    (root / "packages" / "retrieval" / "test_flow_seed_ranking.py").write_text(
        "def test_dart_flow_context_retrieval():\n"
        "    assert 'dart' in 'dart flow test'\n"
        "\n"
        "def test_get_relevant_context_api():\n"
        "    pass\n"
    )


def _setup_one_hop_project(temp_store, project_id: str = "onehop-p"):
    tmpdir = tempfile.mkdtemp()
    root = Path(tmpdir)
    _make_one_hop_tree(root)
    temp_store.add_project(project_id, "OneHop", "", str(root))
    from services.ingestion.index_store import ProjectIndexStore

    ProjectIndexStore(temp_store).sync_project(project_id, str(root))
    return tmpdir, project_id


def test_is_call_delegation_question_intent():
    assert is_call_delegation_question(
        "what does OverhaustAgent.get_relevant_context call?"
    )
    assert is_call_delegation_question(
        "Where is OverhaustAgent.get_relevant_context defined and what does it call?"
    )
    assert is_call_delegation_question(
        "what does get_relevant_context invoke?"
    )
    assert is_call_delegation_question("what calls get_relevant_context?")
    assert not is_call_delegation_question("Where is the KOT generated?")
    assert not is_call_delegation_question(
        "Add support for multiple kitchen printers"
    )


def test_one_hop_expands_invoke_context_request(temp_store):
    tmpdir, pid = _setup_one_hop_project(temp_store)
    try:
        result = assemble_agent_context(
            pid,
            "Where is OverhaustAgent.get_relevant_context defined and what does it call?",
            memory_store=temp_store,
            include_code_flow=False,
        )
        assert not result.insufficient_evidence
        paths = [f.get("path", "") for f in result.relevant_files]
        names = [s.get("name") for s in result.relevant_symbols]
        assert any(p.endswith("autonomous_agent.py") for p in paths)
        assert any(p.endswith("agent_context.py") for p in paths)
        assert "get_relevant_context" in names
        assert "invoke_context_request" in names

        callee_files = [
            f for f in result.relevant_files
            if (f.get("path") or "").endswith("agent_context.py")
        ]
        assert callee_files
        snippet = callee_files[0].get("snippet") or ""
        assert "assemble_agent_context" in snippet
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_one_hop_not_triggered_for_normal_kot_query(temp_store):
    tmpdir = tempfile.mkdtemp()
    try:
        root = Path(tmpdir)
        make_kot_tree(root)
        # Also plant agent_context so a false trigger would surface it.
        (root / "packages" / "context").mkdir(parents=True, exist_ok=True)
        (root / "packages" / "context" / "agent_context.py").write_text(
            "def invoke_context_request(project_id, prompt):\n"
            "    return assemble_agent_context(project_id, prompt)\n"
            "\n"
            "def assemble_agent_context(project_id, prompt):\n"
            "    return {}\n"
        )
        temp_store.add_project("kot-hop", "KotHop", "", str(root))
        from services.ingestion.index_store import ProjectIndexStore

        ProjectIndexStore(temp_store).sync_project("kot-hop", str(root))
        result = assemble_agent_context(
            "kot-hop",
            "Where is the KOT generated?",
            memory_store=temp_store,
            include_code_flow=False,
        )
        names = [s.get("name") for s in result.relevant_symbols]
        paths = [f.get("path", "") for f in result.relevant_files]
        assert "invoke_context_request" not in names
        assert not any(p.endswith("agent_context.py") for p in paths)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_one_hop_respects_budgets(temp_store):
    tmpdir, pid = _setup_one_hop_project(temp_store, "budget-hop")
    try:
        result = assemble_agent_context(
            pid,
            "what does OverhaustAgent.get_relevant_context call?",
            memory_store=temp_store,
            include_code_flow=False,
            max_files=2,
            max_symbols=2,
            max_evidence=2,
        )
        assert len(result.relevant_files) <= 2
        assert len(result.relevant_symbols) <= 2
        assert len(result.evidence) <= 2
        # Primary + callee should win the tight budget.
        names = [s.get("name") for s in result.relevant_symbols]
        assert "get_relevant_context" in names
        assert "invoke_context_request" in names
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_one_hop_prefers_python_callee_over_dart_noise(temp_store):
    tmpdir, pid = _setup_one_hop_project(temp_store, "noise-hop")
    try:
        result = assemble_agent_context(
            pid,
            "what does OverhaustAgent.get_relevant_context call in the dart flow test?",
            memory_store=temp_store,
            include_code_flow=False,
            max_files=4,
            max_symbols=4,
        )
        assert result.relevant_symbols
        top_names = [s.get("name") for s in result.relevant_symbols[:3]]
        top_paths = [s.get("file", "") for s in result.relevant_symbols[:3]]
        assert "get_relevant_context" in top_names
        assert "invoke_context_request" in top_names
        assert any(p.endswith("autonomous_agent.py") for p in top_paths)
        assert any(p.endswith("agent_context.py") for p in top_paths)
        assert not any(p.endswith(".dart") for p in top_paths[:2])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_one_hop_missing_callee_keeps_primary(temp_store):
    tmpdir = tempfile.mkdtemp()
    try:
        root = Path(tmpdir)
        (root / "packages" / "agent").mkdir(parents=True)
        (root / "packages" / "agent" / "autonomous_agent.py").write_text(
            "class OverhaustAgent:\n"
            "    def get_relevant_context(self, project_id, task):\n"
            "        from packages.context.agent_context import missing_callee_symbol\n"
            "        return missing_callee_symbol(project_id, task)\n"
        )
        temp_store.add_project("miss-hop", "Miss", "", str(root))
        from services.ingestion.index_store import ProjectIndexStore

        ProjectIndexStore(temp_store).sync_project("miss-hop", str(root))
        result = assemble_agent_context(
            "miss-hop",
            "what does OverhaustAgent.get_relevant_context call?",
            memory_store=temp_store,
            include_code_flow=False,
        )
        names = [s.get("name") for s in result.relevant_symbols]
        assert "get_relevant_context" in names
        # Unresolvable callee must not be packaged as a one-hop continuation.
        assert not any(
            e.get("reason") == "one-hop callee"
            and e.get("symbol") == "missing_callee_symbol"
            for e in result.evidence
        )
        assert not any(
            (f.get("path") or "").endswith("agent_context.py")
            for f in result.relevant_files
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_is_test_path_detects_test_prefix_modules():
    from packages.context.agent_context import (
        _is_benchmark_or_fixture_path,
        _is_secondary_context_path,
        _is_test_path,
    )

    assert _is_test_path("packages/context/test_agent_context.py")
    assert _is_test_path("packages/agent/test_autonomous_agent.py")
    assert _is_test_path("tests/evaluation/retrieval_benchmark.py")
    assert not _is_test_path("packages/context/agent_context.py")
    assert _is_benchmark_or_fixture_path(
        "benchmark-runs/phase15-20260902T110229Z/overhaust/lib/screens/tables/tables_screen.dart"
    )
    assert _is_secondary_context_path("packages/context/test_agent_context.py")
    assert not _is_secondary_context_path("packages/context/agent_context.py")


def test_prioritize_demotes_tests_and_benchmark_runs():
    from packages.context.agent_context import _prioritize_implementation_hits

    files = [
        {"path": "packages/context/test_agent_context.py", "relevance_score": 9.0},
        {
            "path": "benchmark-runs/phase15/naive/lib/services/hardware/quikot.dart",
            "relevance_score": 8.5,
        },
        {"path": "packages/context/agent_context.py", "relevance_score": 7.0},
        {"path": "packages/shared/config.py", "relevance_score": 6.5},
    ]
    symbols = [
        {"name": "test_context_budget_limits", "file": "packages/context/test_agent_context.py"},
        {"name": "_clamp_budget", "file": "packages/context/agent_context.py"},
        {"name": "get_context_max_files", "file": "packages/shared/config.py"},
    ]
    ordered_files, ordered_symbols = _prioritize_implementation_hits(
        files, symbols, "general", max_files=4, max_symbols=3,
    )
    assert ordered_files[0]["path"] == "packages/context/agent_context.py"
    assert ordered_files[1]["path"] == "packages/shared/config.py"
    assert ordered_symbols[0]["name"] == "_clamp_budget"
    assert {s["name"] for s in ordered_symbols[:2]} <= {
        "_clamp_budget", "get_context_max_files",
    }


def test_change_oriented_prompt_classified_as_development():
    from packages.context.agent_context import _analyze_task

    analysis = _analyze_task(
        "If I wanted to change how the context budget is enforced, "
        "which files and functions would I need to modify?"
    )
    assert analysis["task_type"] == "development"
