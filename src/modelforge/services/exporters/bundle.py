"""Reproducibility bundle exporter (spec 28.3 / Appendix F).

Builds ``exports/modelforge_run_{run_id}.zip`` containing the report, code,
figures/tables, metrics, evidence, citations, logs, manifests, and (when
required) the AI disclosure. Also writes the reproducibility manifest with input
hashes, code hashes, seeds, experiments, metrics, evidence, citations, and human
approvals (spec 18 manifest fields).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from modelforge.common.timeutil import isoformat
from modelforge.schemas.artifacts import ReproducibilityManifest
from modelforge.schemas.enums import ArtifactType
from modelforge.schemas.state import ModelingState
from modelforge.storage.repositories.artifact_registry import ArtifactRegistry

# artifact_type -> folder inside the bundle
_BUNDLE_DIRS = {
    ArtifactType.REPORT_MARKDOWN: "",
    ArtifactType.REPORT_LATEX: "",
    ArtifactType.REPORT_PDF: "",
    ArtifactType.FIGURE: "figures",
    ArtifactType.TABLE: "tables",
    ArtifactType.METRICS_FILE: "metrics",
    ArtifactType.SCRIPT: "code",
    ArtifactType.DEPENDENCY_LOCK: "code",
    ArtifactType.NOTEBOOK: "notebooks",
    ArtifactType.EXECUTION_LOG: "logs",
    ArtifactType.EVIDENCE_RECORD: "evidence",
    ArtifactType.CITATION_RECORD: "citations",
    ArtifactType.DISCLOSURE_RECORD: "",
}


class BundleExporter:
    def __init__(self, registry: ArtifactRegistry) -> None:
        self.registry = registry

    def build_manifest(self, state: ModelingState) -> ReproducibilityManifest:
        input_hashes = {}
        if state.input_manifest:
            input_hashes = {
                f.normalized_name: f.content_hash for f in state.input_manifest.files
            }
        code_hashes = {a.code_artifact_id: a.content_hash for a in state.code_artifacts}
        deps: list[str] = []
        for a in state.code_artifacts:
            deps.extend(a.dependencies)
        seeds = {e.experiment_id: e.seed for e in state.experiment_records}
        metrics = {
            e.experiment_id: e.metrics for e in state.experiment_records if e.metrics
        }
        human_approvals = [
            {
                "checkpoint_id": fb.checkpoint_id,
                "user_id": fb.user_id,
                "action": fb.action.value,
                "timestamp": isoformat(fb.timestamp),
            }
            for fb in state.human_feedback
        ]
        return ReproducibilityManifest(
            run_id=state.run_id,
            mode=state.mode,
            competition_profile_id=(
                state.competition_profile.profile_id if state.competition_profile else None
            ),
            input_file_hashes=input_hashes,
            code_artifact_hashes=code_hashes,
            dependencies=sorted(set(deps)),
            seeds=seeds,
            experiments=[e.experiment_id for e in state.experiment_records],
            metrics=metrics,
            evidence_claim_ids=[c.claim_id for c in state.evidence_claims],
            citation_ids=[c.citation_id for c in state.citations],
            human_approvals=human_approvals,
        )

    def export(
        self,
        state: ModelingState,
        *,
        disclosure_required: bool = False,
    ) -> tuple[bytes, ReproducibilityManifest]:
        """Build the ZIP bundle bytes + manifest for a run."""
        manifest = self.build_manifest(state)
        buf = io.BytesIO()
        used_names: set[str] = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Registered artifacts.
            for artifact in self.registry.list_for_run(state.run_id):
                folder = _BUNDLE_DIRS.get(artifact.artifact_type)
                if folder is None:
                    continue
                if (
                    artifact.artifact_type == ArtifactType.DISCLOSURE_RECORD
                    and not disclosure_required
                ):
                    continue
                try:
                    data = self.registry.read_bytes(artifact.artifact_id)
                except OSError:  # skip unreadable artifacts
                    continue
                arcname = f"{folder}/{artifact.filename}" if folder else artifact.filename
                arcname = _unique_arcname(arcname, artifact.artifact_id, used_names)
                zf.writestr(arcname, data)

            # Manifests.
            zf.writestr(
                "reproducibility_manifest.json",
                json.dumps(manifest.model_dump(mode="json"), indent=2),
            )
            if state.input_manifest:
                zf.writestr(
                    "input_manifest.json",
                    json.dumps(state.input_manifest.model_dump(mode="json"), indent=2),
                )
            artifact_index = [
                a.model_dump(mode="json") for a in self.registry.list_for_run(state.run_id)
            ]
            zf.writestr("artifact_manifest.json", json.dumps(artifact_index, indent=2))

            # Evidence + citations as consolidated JSON for convenience.
            zf.writestr(
                "evidence/claims.json",
                json.dumps([c.model_dump(mode="json") for c in state.evidence_claims], indent=2),
            )
            zf.writestr(
                "citations/citations.json",
                json.dumps([c.model_dump(mode="json") for c in state.citations], indent=2),
            )

        return buf.getvalue(), manifest

    def export_to_file(
        self, state: ModelingState, out_path: Path, *, disclosure_required: bool = False
    ) -> ReproducibilityManifest:
        data, manifest = self.export(state, disclosure_required=disclosure_required)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return manifest


def _unique_arcname(arcname: str, artifact_id: str, used: set[str]) -> str:
    """Disambiguate colliding bundle paths by inserting the artifact id segment.

    Multiple experiments can emit files with the same name (e.g. metrics.json);
    each must appear distinctly in the bundle, never silently overwritten.
    """
    if arcname not in used:
        used.add(arcname)
        return arcname
    suffix = artifact_id.rsplit("_", 1)[-1]
    if "." in arcname:
        stem, ext = arcname.rsplit(".", 1)
        candidate = f"{stem}_{suffix}.{ext}"
    else:
        candidate = f"{arcname}_{suffix}"
    used.add(candidate)
    return candidate
