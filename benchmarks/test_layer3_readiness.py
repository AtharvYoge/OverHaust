"""Fixture size, restoration, and fail-closed Layer 3 readiness."""

import json
from pathlib import Path

import httpx
import pytest

from benchmarks.experiment import run_layer3_live
from benchmarks.layer3.readiness import ExperimentIntegrityError, validate_layer3_live_ready
from benchmarks.layer3.runner import OpenAICompatibleRunner, run_layer3_pair
from benchmarks.repos import prepare_sized_fixture
from benchmarks.repro import capture_repository_snapshot, restore_repository_snapshot
from benchmarks.tasks_loader import load_task_set


class _ScriptedTransport(httpx.BaseTransport):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content.decode("utf-8")))
        body = self.responses.pop(0)
        return httpx.Response(200, json=body)


def _final(content="ok"):
    return {
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
    }


def _runner():
    return OpenAICompatibleRunner(
        api_key="test-key",
        transport=_ScriptedTransport([_final(), _final()]),
        model="gpt-4o-mini",
        temperature=0.0,
        seed=1,
        max_tool_calls=2,
        timeout_s=30,
    )


@pytest.mark.parametrize("size", ["small", "medium", "large"])
def test_trace_repository_size_matches_fixture(size, tmp_path: Path):
    fixture = prepare_sized_fixture(size, root=tmp_path / size)
    task = next(t for t in load_task_set("initial") if t.task_id == "sym_generate_kot")
    assert task.repository_size == "medium"
    runner = _runner()
    result = run_layer3_pair(
        task,
        repository_root=str(fixture.root),
        overhaust_context="OverHaust repository context sample",
        runner=runner,
        repository_size=fixture.repository_size,
    )
    assert result["isolation_proven"] is True
    assert result["baseline"].repository_size == size
    assert result["overhaust"].repository_size == size
    assert all(item["status"] == "KNOWN" and item["verified"] is True for item in result["repository_restore"])
    fixture.close()


def test_snapshot_restores_mutated_fixture(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    snapshot = capture_repository_snapshot(str(tmp_path))
    (tmp_path / "a.py").write_text("x=2\n", encoding="utf-8")
    (tmp_path / "extra.py").write_text("y=1\n", encoding="utf-8")
    status = restore_repository_snapshot(str(tmp_path), snapshot)
    assert status["status"] == "KNOWN"
    assert status["verified"] is True
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x=1\n"
    assert not (tmp_path / "extra.py").exists()


def test_snapshot_restore_failure_is_not_known(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    snapshot = capture_repository_snapshot(str(tmp_path))
    status = restore_repository_snapshot(str(tmp_path / "missing"), snapshot)
    assert status["status"] == "UNAVAILABLE"
    assert status["verified"] is False


def test_pair_does_not_call_provider_when_restore_unproven(tmp_path: Path, monkeypatch):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    task = next(t for t in load_task_set("initial") if t.task_id == "sym_generate_kot")
    transport = _ScriptedTransport([_final(), _final()])
    runner = OpenAICompatibleRunner(
        api_key="test-key", transport=transport, model="gpt-4o-mini", max_tool_calls=2,
    )

    def _unproven(path, snapshot=None):
        return {"status": "UNAVAILABLE", "verified": False, "mechanism": "content_snapshot"}

    monkeypatch.setattr("benchmarks.repro.isolate_repository", _unproven)
    result = run_layer3_pair(
        task,
        repository_root=str(tmp_path),
        overhaust_context="ctx",
        runner=runner,
        repository_size="small",
    )
    assert transport.requests == []
    assert result["isolation_proven"] is False
    assert result["validation"]["comparable"] is False
    assert result["validation"]["allow_exact_token_reduction"] is False
    assert result["baseline"] is None
    assert result["overhaust"] is None


def test_readiness_fails_closed_on_size_mismatch():
    task = next(t for t in load_task_set("initial") if t.task_id == "sym_generate_kot")
    with pytest.raises(ExperimentIntegrityError):
        validate_layer3_live_ready(
            model="gpt-4o-mini",
            tasks=[task],
            requested_repo_size="small",
            fixture_repository_size="medium",
            restore_status={"status": "KNOWN", "verified": True},
            tool_set_hash_value="abc",
            temperature=0.0,
            max_tool_calls=4,
            timeout_s=30,
            max_output_tokens=128,
        )


def test_dry_run_small_does_not_call_provider(tmp_path: Path):
    report = run_layer3_live(
        task_ids=["sym_generate_kot"],
        runs=1,
        repo_size="small",
        dry_run=True,
        results_dir=tmp_path,
    )
    assert report["dry_run"] is True
    assert report["repo_size"] == "small"
    assert report["fixture_repository_size"] == "small"
    assert report["pairs"] == []
    assert report["repository_restore_probe"]["status"] == "KNOWN"
    assert report["repository_restore_probe"]["verified"] is True
    assert report["readiness"]["ok"] is True
    assert list(tmp_path.glob("layer3-live-*.json")) == []
