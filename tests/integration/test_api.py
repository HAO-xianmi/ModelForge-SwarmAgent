"""Phase G: FastAPI endpoint tests using TestClient (real workflow, mock LLM)."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

TINY_CSV = (
    "f0,f1,target\n"
    + "\n".join(f"{i * 0.1},{i * 0.2},{i * 0.5}" for i in range(40))
    + "\n"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELFORGE_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("MODELFORGE_LLM", "mock")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    from modelforge.api import dependencies
    from modelforge.common import config

    config.get_settings.cache_clear()
    dependencies.get_database.cache_clear()
    from modelforge.api.main import app

    with TestClient(app) as c:
        yield c
    config.get_settings.cache_clear()
    dependencies.get_database.cache_clear()


def test_health(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_run(client) -> None:
    r = client.post("/api/v1/runs", json={"mode": "practice", "competition_profile_id": "practice"})
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"].startswith("run_")
    assert body["status"] == "CREATED"


def test_methods_and_profiles_endpoints(client) -> None:
    r = client.get("/api/v1/methods")
    assert r.status_code == 200
    assert len(r.json()) >= 20
    r2 = client.get("/api/v1/methods/linear_regression")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Linear Regression"
    r3 = client.get("/api/v1/profiles/practice")
    assert r3.status_code == 200
    assert r3.json()["profile_id"] == "practice_v1"
    assert client.get("/api/v1/methods/nope").status_code == 404


def test_full_run_via_api(client) -> None:
    created = client.post("/api/v1/runs", json={"competition_profile_id": "practice"})
    run_id = created.json()["run_id"]
    # Upload files.
    files = [
        ("files", ("problem.txt", b"Forecast target from features. Report RMSE.", "text/plain")),
        ("files", ("data.csv", TINY_CSV.encode(), "text/csv")),
    ]
    r = client.post(f"/api/v1/runs/{run_id}/files", files=files)
    assert r.status_code == 200
    assert "data.csv" in r.json()["files"]

    # Start (practice mode runs to completion).
    r = client.post(f"/api/v1/runs/{run_id}/start")
    assert r.status_code == 200
    assert r.json()["status"] == "COMPLETED", r.json()

    # Inspect state, events, artifacts.
    state = client.get(f"/api/v1/runs/{run_id}/state").json()
    assert state["status"] == "COMPLETED"
    events = client.get(f"/api/v1/runs/{run_id}/events").json()
    assert any(e["event_type"] == "RUN_COMPLETED" for e in events)
    artifacts = client.get(f"/api/v1/runs/{run_id}/artifacts").json()
    assert any(a["artifact_type"] == "REPORT_MARKDOWN" for a in artifacts)

    # Export download.
    exports = client.get(f"/api/v1/runs/{run_id}/exports").json()
    assert exports["bundle_path"]
    dl = client.get(f"/api/v1/runs/{run_id}/exports/download")
    assert dl.status_code == 200
    with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
        assert "report.md" in zf.namelist()


def test_contest_run_checkpoint_flow_via_api(client) -> None:
    run_id = client.post(
        "/api/v1/runs",
        json={"mode": "contest_compliant", "competition_profile_id": "generic_contest"},
    ).json()["run_id"]
    files = [
        ("files", ("problem.txt", b"Forecast target. Report RMSE.", "text/plain")),
        ("files", ("data.csv", TINY_CSV.encode(), "text/csv")),
    ]
    client.post(f"/api/v1/runs/{run_id}/files", files=files)
    r = client.post(f"/api/v1/runs/{run_id}/start")
    assert r.json()["status"] == "WAITING_FOR_CHECKPOINT_1"

    # Resolve all three checkpoints.
    for _ in range(5):
        cps = client.get(f"/api/v1/runs/{run_id}/checkpoints").json()
        if cps["pending"] is None:
            break
        cp_id = cps["pending"]["checkpoint_id"]
        r = client.post(
            f"/api/v1/runs/{run_id}/checkpoints/{cp_id}/resolve",
            json={"action": "APPROVE"},
        )
        assert r.status_code == 200
    final = client.get(f"/api/v1/runs/{run_id}").json()
    assert final["status"] == "COMPLETED", final


def test_cancel_run(client) -> None:
    created = client.post("/api/v1/runs", json={"competition_profile_id": "practice"})
    run_id = created.json()["run_id"]
    r = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"


def test_unknown_run_404(client) -> None:
    assert client.get("/api/v1/runs/run_nope").status_code == 404
    assert client.get("/api/v1/runs/run_nope/state").status_code == 404
