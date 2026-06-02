"""Phase A smoke tests: common utilities."""

from __future__ import annotations

import re

import pytest

from modelforge.common import hashing, ids
from modelforge.common.config import (
    LLMBackend,
    SandboxBackend,
    Settings,
    validate_environment,
)
from modelforge.common.errors import (
    FailureType,
    ModelForgeError,
    SandboxPolicyError,
)
from modelforge.common.logging import JsonlEventLogger
from modelforge.common.timeutil import isoformat, parse_iso, utcnow


def test_utcnow_is_timezone_aware() -> None:
    now = utcnow()
    assert now.tzinfo is not None


def test_isoformat_roundtrip() -> None:
    now = utcnow()
    text = isoformat(now)
    assert text.endswith("Z")
    back = parse_iso(text)
    assert abs((back - now).total_seconds()) < 1e-3


def test_run_id_format() -> None:
    rid = ids.new_run_id()
    assert re.fullmatch(r"run_\d{14}_[0-9a-f]{8}", rid)


def test_artifact_id_includes_type() -> None:
    aid = ids.new_artifact_id("PROBLEM_CARD")
    assert aid.startswith("artifact_problem_card_")


def test_ids_are_unique() -> None:
    assert len({ids.new_claim_id() for _ in range(1000)}) == 1000


def test_slugify() -> None:
    assert ids.slugify("Hello, World!") == "hello_world"
    assert ids.slugify("   ") == "x"


def test_hash_bytes_deterministic() -> None:
    assert hashing.hash_bytes(b"abc") == hashing.hash_bytes(b"abc")
    assert hashing.hash_bytes(b"abc") != hashing.hash_bytes(b"abd")


def test_hash_json_order_independent() -> None:
    assert hashing.hash_json({"a": 1, "b": 2}) == hashing.hash_json({"b": 2, "a": 1})


def test_hash_file(tmp_path) -> None:
    p = tmp_path / "data.txt"
    p.write_bytes(b"reproducible")
    assert hashing.hash_file(p) == hashing.hash_bytes(b"reproducible")


def test_error_to_dict_classifies() -> None:
    err = SandboxPolicyError("path escape", context={"path": "../etc"})
    d = err.to_dict()
    assert d["failure_type"] == FailureType.POLICY_FAILURE.value
    assert d["context"]["path"] == "../etc"
    assert isinstance(err, ModelForgeError)


def test_jsonl_event_logger(tmp_path) -> None:
    logger = JsonlEventLogger(tmp_path / "logs" / "workflow.jsonl")
    logger.emit("RUN_CREATED", run_id="run_x")
    logger.emit("PROBLEM_PARSED", run_id="run_x", confidence=0.9)
    events = logger.read_all()
    assert [e["event_type"] for e in events] == ["RUN_CREATED", "PROBLEM_PARSED"]
    assert all("ts" in e for e in events)


def test_settings_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MODELFORGE_RUNS_DIR", str(tmp_path / "runs"))
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.llm is LLMBackend.MOCK
    assert s.sandbox is SandboxBackend.AUTO
    assert s.max_upload_bytes == s.max_upload_mb * 1024 * 1024


def test_validate_environment_mock_ok(tmp_path) -> None:
    s = Settings(_env_file=None, runs_dir=tmp_path / "runs", llm=LLMBackend.MOCK)  # type: ignore[call-arg]
    checks = validate_environment(s)
    assert all(c.ok for c in checks)


def test_validate_environment_openai_requires_key(tmp_path) -> None:
    s = Settings(  # type: ignore[call-arg]
        _env_file=None, runs_dir=tmp_path / "runs", llm=LLMBackend.OPENAI
    )
    checks = {c.name: c for c in validate_environment(s)}
    assert checks["openai_api_key"].ok is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
