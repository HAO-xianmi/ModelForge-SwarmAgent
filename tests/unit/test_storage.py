"""Phase C: storage, artifact registry, state versioning, audit, run directory."""

from __future__ import annotations

import pytest

from modelforge.common.errors import InputError
from modelforge.common.hashing import hash_bytes
from modelforge.common.ids import new_run_id
from modelforge.schemas.enums import ActorType, ArtifactType, EventType, RunStatus
from modelforge.schemas.state import ModelingState, Run
from modelforge.storage.run_directory import RUN_SUBDIRS


# --------------------------------------------------------------------------- #
# Run directory
# --------------------------------------------------------------------------- #
def test_run_directory_creates_all_subdirs(make_run_dir) -> None:
    rid = new_run_id()
    rd = make_run_dir(rid)
    assert rd.exists()
    for sub in RUN_SUBDIRS:
        assert (rd.path / sub).is_dir()


def test_run_directory_rejects_traversal(make_run_dir) -> None:
    rid = new_run_id()
    rd = make_run_dir(rid)
    with pytest.raises(InputError):
        rd.resolve_within("..", "..", "etc", "passwd")


# --------------------------------------------------------------------------- #
# Artifact registry
# --------------------------------------------------------------------------- #
def test_artifact_register_and_hash(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    data = b'{"title": "demo"}'
    art = registry.register_bytes(rid, ArtifactType.PROBLEM_CARD, "problem_card.json", data)
    assert art.content_hash == hash_bytes(data)
    assert art.size_bytes == len(data)
    # Round-trips from the object store.
    assert registry.read_bytes(art.artifact_id) == data
    # Indexed and retrievable.
    fetched = registry.get(art.artifact_id)
    assert fetched is not None and fetched.artifact_id == art.artifact_id


def test_artifact_filename_sanitized(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    art = registry.register_bytes(
        rid, ArtifactType.SCRIPT, "../../evil name!.py", b"print(1)"
    )
    assert "/" not in art.filename and "\\" not in art.filename
    assert art.filename == "evilname.py"


def test_artifact_immutable_revision_creates_new_id(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    v1 = registry.register_text(rid, ArtifactType.REPORT_MARKDOWN, "report.md", "v1")
    v2 = registry.revise(v1, b"v2")
    assert v2.artifact_id != v1.artifact_id
    assert v1.artifact_id in v2.source_artifact_ids
    assert v2.metadata["revises"] == v1.artifact_id
    # Original bytes are untouched.
    assert registry.read_bytes(v1.artifact_id) == b"v1"
    assert registry.read_bytes(v2.artifact_id) == b"v2"


def test_artifact_list_filtered_by_type(registry, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    registry.register_text(rid, ArtifactType.FIGURE, "f1.png", "x")
    registry.register_text(rid, ArtifactType.METRICS_FILE, "m.json", "{}")
    figures = registry.list_for_run(rid, ArtifactType.FIGURE)
    assert len(figures) == 1 and figures[0].artifact_type is ArtifactType.FIGURE


# --------------------------------------------------------------------------- #
# Run + state versioning
# --------------------------------------------------------------------------- #
def test_create_run_and_initial_version(run_repo) -> None:
    rid = new_run_id()
    run = Run(run_id=rid, mode="practice")
    run_repo.create_run(run, ModelingState(run_id=rid))
    assert run_repo.get_run(rid) is not None
    assert run_repo.current_version(rid) == 0
    assert run_repo.list_versions(rid) == [0]


def test_save_state_increments_version_and_records_change(run_repo) -> None:
    rid = new_run_id()
    run_repo.create_run(Run(run_id=rid), ModelingState(run_id=rid))

    state = run_repo.load_state(rid)
    assert state is not None
    state.status = RunStatus.PARSING
    change = run_repo.save_state(
        state, actor="supervisor", actor_type=ActorType.SYSTEM, reason="advance to parsing"
    )
    assert change.previous_version == 0
    assert change.new_version == 1
    assert "status" in change.changed_fields
    assert run_repo.current_version(rid) == 1
    # Old version is preserved (immutable history).
    old = run_repo.load_state(rid, version=0)
    assert old is not None and old.status is RunStatus.CREATED


def test_human_edits_distinguishable_from_machine(run_repo, audit_repo) -> None:
    rid = new_run_id()
    run_repo.create_run(Run(run_id=rid), ModelingState(run_id=rid))
    state = run_repo.load_state(rid)
    assert state is not None
    state.status = RunStatus.RETRIEVING_METHODS
    run_repo.save_state(
        state, actor="alice", actor_type=ActorType.HUMAN, reason="human override"
    )
    events = audit_repo.list_for_run(rid)
    state_events = [e for e in events if e.event_type is EventType.STATE_UPDATED]
    assert state_events[-1].actor_type is ActorType.HUMAN
    assert state_events[-1].actor_id == "alice"


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def test_audit_records_and_orders(audit_repo) -> None:
    rid = new_run_id()
    audit_repo.record(rid, EventType.RUN_CREATED, payload={"a": 1})
    audit_repo.record(rid, EventType.PROBLEM_PARSED, payload={"confidence": 0.9})
    events = audit_repo.list_for_run(rid)
    assert [e.event_type for e in events] == [
        EventType.RUN_CREATED,
        EventType.PROBLEM_PARSED,
    ]
    assert events[1].payload["confidence"] == 0.9
