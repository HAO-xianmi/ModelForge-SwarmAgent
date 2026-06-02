"""Evidence Registry (spec 12).

Registers claims, validates that quantitative claims actually link to an
experiment and to metric values that came from that experiment, links claims to
artifacts/citations, and exposes a writer-access filter. It NEVER fabricates a
metric: ``register_quantitative`` requires the value to be supplied from an
executed experiment's metrics (working rule 5).
"""

from __future__ import annotations

from modelforge.common.errors import QualityGateError
from modelforge.common.ids import new_claim_id
from modelforge.schemas.enums import ClaimStatus, ClaimType
from modelforge.schemas.evidence import CitationRecord, EvidenceClaim
from modelforge.schemas.experiment import ExperimentRecord


class EvidenceRegistry:
    """In-state evidence registry operating on a run's claim list.

    The authoritative store is the blackboard ``ModelingState.evidence_claims``;
    this service produces/validates the claim objects that the workflow then
    persists via the run repository.
    """

    def register_quantitative(
        self,
        run_id: str,
        statement: str,
        *,
        experiment: ExperimentRecord,
        metric_name: str,
        artifact_ids: list[str] | None = None,
        claim_type: ClaimType = ClaimType.QUANTITATIVE_RESULT,
    ) -> EvidenceClaim:
        """Register a quantitative claim backed by a real experiment metric.

        Raises if the named metric is not present in the experiment's recorded
        metrics — preventing claims about numbers that were never measured.
        """
        if metric_name not in experiment.metrics:
            raise QualityGateError(
                "quantitative claim references a metric not produced by the experiment",
                context={
                    "metric": metric_name,
                    "available": sorted(experiment.metrics),
                    "experiment_id": experiment.experiment_id,
                },
            )
        value = experiment.metrics[metric_name]
        return EvidenceClaim(
            claim_id=new_claim_id(),
            run_id=run_id,
            claim_type=claim_type,
            statement=statement,
            verification_status=ClaimStatus.PENDING,
            experiment_id=experiment.experiment_id,
            metric_name=metric_name,
            metric_value=value,
            artifact_ids=artifact_ids or [],
        )

    def register_comparison(
        self,
        run_id: str,
        statement: str,
        *,
        experiment: ExperimentRecord,
        metric_name: str,
        baseline_value: float,
        selected_value: float,
        artifact_ids: list[str] | None = None,
    ) -> EvidenceClaim:
        claim = EvidenceClaim(
            claim_id=new_claim_id(),
            run_id=run_id,
            claim_type=ClaimType.MODEL_COMPARISON,
            statement=statement,
            verification_status=ClaimStatus.PENDING,
            experiment_id=experiment.experiment_id,
            metric_name=metric_name,
            metric_value={"baseline": baseline_value, "selected_model": selected_value},
            artifact_ids=artifact_ids or [],
        )
        return claim

    def register_qualitative(
        self,
        run_id: str,
        statement: str,
        claim_type: ClaimType,
        *,
        artifact_ids: list[str] | None = None,
        citation_ids: list[str] | None = None,
        status: ClaimStatus = ClaimStatus.PENDING,
        source_notes: str = "",
    ) -> EvidenceClaim:
        return EvidenceClaim(
            claim_id=new_claim_id(),
            run_id=run_id,
            claim_type=claim_type,
            statement=statement,
            verification_status=status,
            artifact_ids=artifact_ids or [],
            citation_ids=citation_ids or [],
            source_notes=source_notes,
        )

    # ------------------------------------------------------------------ #
    # Verification
    # ------------------------------------------------------------------ #
    def verify(
        self,
        claim: EvidenceClaim,
        experiments: list[ExperimentRecord],
        *,
        verified_by: str = "experiment_auditor",
    ) -> EvidenceClaim:
        """Verify or reject a claim against the experiment record set.

        A quantitative/comparison claim is VERIFIED only if its experiment
        exists, succeeded, and still contains the cited metric. Otherwise it is
        REJECTED. Qualitative claims pass through unless already decided.
        """
        if claim.is_quantitative or claim.claim_type is ClaimType.MODEL_COMPARISON:
            exp = next(
                (e for e in experiments if e.experiment_id == claim.experiment_id), None
            )
            ok = (
                exp is not None
                and exp.status.value == "SUCCEEDED"
                and claim.metric_name is not None
                and claim.metric_name in exp.metrics
            )
            new_status = ClaimStatus.VERIFIED if ok else ClaimStatus.REJECTED
            return claim.model_copy(
                update={"verification_status": new_status, "verified_by": verified_by}
            )
        # Non-quantitative claims keep their assigned status; mark verified if pending.
        if claim.verification_status is ClaimStatus.PENDING:
            return claim.model_copy(
                update={
                    "verification_status": ClaimStatus.VERIFIED,
                    "verified_by": verified_by,
                }
            )
        return claim

    def link_citation(self, claim: EvidenceClaim, citation: CitationRecord) -> EvidenceClaim:
        ids = sorted({*claim.citation_ids, citation.citation_id})
        return claim.model_copy(update={"citation_ids": ids})

    # ------------------------------------------------------------------ #
    # Writer access filter (spec 12.5)
    # ------------------------------------------------------------------ #
    @staticmethod
    def writer_usable(claims: list[EvidenceClaim]) -> list[EvidenceClaim]:
        return [c for c in claims if c.usable_by_writer]
