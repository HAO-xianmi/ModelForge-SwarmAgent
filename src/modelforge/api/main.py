"""FastAPI application (spec 26).

Exposes the run lifecycle, state/events/artifacts inspection, checkpoint
resolution, cancellation, and exports — plus method-library and profile lookups.
Background workflow execution runs in a thread pool so long sandbox steps do not
block the event loop; clients poll ``GET /runs/{id}`` for status.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import Request

from modelforge.api.dependencies import get_coordinator
from modelforge.api.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    ResolveCheckpointRequest,
    RunSummary,
)
from modelforge.common.errors import ModelForgeError
from modelforge.graph.coordinator import RunCoordinator
from modelforge.schemas.enums import CheckpointAction
from modelforge.services.compliance import load_profile
from modelforge.services.ingestion import UploadedFile
from modelforge.services.method_library import get_method_library

app = FastAPI(
    title="ModelForge-Swarm API",
    version="0.1.0",
    description="Auditable multi-agent copilot for mathematical modeling.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Workflow execution can be long (real sandbox runs); run off the event loop.
_executor = ThreadPoolExecutor(max_workers=2)

Coordinator = Annotated[RunCoordinator, Depends(get_coordinator)]


@app.exception_handler(ModelForgeError)
async def _mf_error_handler(_request: Request, exc: ModelForgeError) -> JSONResponse:
    return JSONResponse(status_code=400, content=exc.to_dict())


@app.exception_handler(ValueError)
async def _value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=404, content={"error": "ValueError", "detail": str(exc)}
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "modelforge-swarm"}


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #
@app.post("/api/v1/runs", response_model=CreateRunResponse)
def create_run(req: CreateRunRequest, coord: Coordinator) -> CreateRunResponse:
    run = coord.create_run(
        mode=req.mode,
        competition_profile=req.competition_profile_id,
        budget_profile=req.budget_profile,
    )
    return CreateRunResponse(run_id=run.run_id, status=run.status.value)


@app.post("/api/v1/runs/{run_id}/files")
async def upload_files(
    run_id: str, coord: Coordinator, files: list[UploadFile] = File(...)
) -> dict:
    uploads = []
    for f in files:
        data = await f.read()
        uploads.append(UploadedFile(filename=f.filename or "upload.bin", data=data))
    state = coord.add_files(run_id, uploads)
    names = [m.normalized_name for m in state.input_manifest.files] if state.input_manifest else []
    return {"run_id": run_id, "files": names}


@app.post("/api/v1/runs/{run_id}/start")
def start_run(run_id: str, coord: Coordinator) -> RunSummary:
    # Run synchronously to a checkpoint pause or completion. (For very long runs,
    # a queue worker would be used; the synchronous path keeps the MVP simple.)
    future = _executor.submit(coord.start, run_id)
    future.result()
    return _summary(run_id, coord)


@app.get("/api/v1/runs/{run_id}", response_model=RunSummary)
def get_run(run_id: str, coord: Coordinator) -> RunSummary:
    return _summary(run_id, coord)


@app.get("/api/v1/runs/{run_id}/state")
def get_state(run_id: str, coord: Coordinator) -> dict:
    state = coord.get_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    return state.model_dump(mode="json")


@app.get("/api/v1/runs/{run_id}/events")
def get_events(run_id: str, coord: Coordinator) -> list[dict]:
    events = coord.run_repo.audit.list_for_run(run_id)
    return [e.model_dump(mode="json") for e in events]


@app.get("/api/v1/runs/{run_id}/artifacts")
def get_artifacts(run_id: str, coord: Coordinator) -> list[dict]:
    from modelforge.storage.repositories import ArtifactRegistry

    registry = ArtifactRegistry(coord.db)
    return [a.model_dump(mode="json") for a in registry.list_for_run(run_id)]


@app.get("/api/v1/runs/{run_id}/checkpoints")
def get_checkpoints(run_id: str, coord: Coordinator) -> dict:
    state = coord.get_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "pending": state.pending_checkpoint.model_dump(mode="json")
        if state.pending_checkpoint
        else None,
        "resolved": [fb.model_dump(mode="json") for fb in state.human_feedback],
    }


@app.post("/api/v1/runs/{run_id}/checkpoints/{checkpoint_id}/resolve")
def resolve_checkpoint(
    run_id: str,
    checkpoint_id: str,
    req: ResolveCheckpointRequest,
    coord: Coordinator,
) -> RunSummary:
    try:
        action = CheckpointAction(req.action)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid action: {req.action}") from exc
    future = _executor.submit(
        coord.resolve_checkpoint,
        run_id,
        checkpoint_id,
        action,
        user_id=req.user_id,
        comments=req.comments,
        edits=req.edits,
    )
    future.result()
    return _summary(run_id, coord)


@app.post("/api/v1/runs/{run_id}/cancel")
def cancel_run(run_id: str, coord: Coordinator) -> RunSummary:
    coord.cancel(run_id)
    return _summary(run_id, coord)


@app.get("/api/v1/runs/{run_id}/exports")
def list_exports(run_id: str, coord: Coordinator) -> dict:
    state = coord.get_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "bundle_artifact_id": state.export_state.bundle_artifact_id,
        "bundle_path": state.export_state.bundle_path,
        "exported_at": state.export_state.exported_at.isoformat()
        if state.export_state.exported_at
        else None,
    }


@app.get("/api/v1/runs/{run_id}/exports/download")
def download_export(run_id: str, coord: Coordinator) -> FileResponse:
    state = coord.get_state(run_id)
    if state is None or not state.export_state.bundle_path:
        raise HTTPException(status_code=404, detail="no export available")
    return FileResponse(
        state.export_state.bundle_path,
        media_type="application/zip",
        filename=f"modelforge_run_{run_id}.zip",
    )


# --------------------------------------------------------------------------- #
# Method library & profiles (read-only)
# --------------------------------------------------------------------------- #
@app.get("/api/v1/methods")
def list_methods() -> list[dict]:
    return [
        {"method_id": m.method_id, "name": m.name, "category": m.category.value}
        for m in get_method_library().all()
    ]


@app.get("/api/v1/methods/{method_id}")
def get_method(method_id: str) -> dict:
    method = get_method_library().get(method_id)
    if method is None:
        raise HTTPException(status_code=404, detail="method not found")
    return method.model_dump(mode="json")


@app.get("/api/v1/profiles/{profile_id}")
def get_profile(profile_id: str) -> dict:
    try:
        profile = load_profile(profile_id)
    except ModelForgeError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    return profile.model_dump(mode="json")


# --------------------------------------------------------------------------- #
def _summary(run_id: str, coord: RunCoordinator) -> RunSummary:
    run = coord.run_repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    state = coord.get_state(run_id)
    cost = state.budget_state.estimated_cost_usd if state else 0.0
    runtime = state.budget_state.sandbox_runtime_seconds if state else 0.0
    return RunSummary(
        run_id=run.run_id,
        mode=run.mode,
        status=run.status.value,
        competition_profile_id=run.competition_profile_id,
        current_state_version=run.current_state_version,
        total_cost_estimate=cost,
        total_runtime_seconds=runtime,
    )
