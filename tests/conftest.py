"""Shared pytest fixtures: isolated DB + run directory per test."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from modelforge.common import config
from modelforge.storage.database import Database
from modelforge.storage.object_store import LocalObjectStore
from modelforge.storage.repositories import ArtifactRegistry, AuditRepository, RunRepository
from modelforge.storage.run_directory import RunDirectory


@pytest.fixture()
def runs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the global settings at a temp runs directory."""
    root = tmp_path / "runs"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MODELFORGE_RUNS_DIR", str(root))
    config.get_settings.cache_clear()
    yield root
    config.get_settings.cache_clear()


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    database.create_all()
    yield database
    database.drop_all()


@pytest.fixture()
def object_store(runs_root: Path) -> LocalObjectStore:
    return LocalObjectStore(root=runs_root)


@pytest.fixture()
def registry(db: Database, object_store: LocalObjectStore) -> ArtifactRegistry:
    return ArtifactRegistry(db, object_store)


@pytest.fixture()
def run_repo(db: Database) -> RunRepository:
    return RunRepository(db)


@pytest.fixture()
def audit_repo(db: Database) -> AuditRepository:
    return AuditRepository(db)


@pytest.fixture()
def make_run_dir(runs_root: Path):
    def _make(run_id: str) -> RunDirectory:
        return RunDirectory(run_id, root=runs_root).create()

    return _make
