"""Evidence Registry service (spec 9.6 / 12) — a hard requirement.

Report generation is evidence-constrained from the start: the writer may only
use VERIFIED claims (and explicitly-marked NEEDS_HUMAN_REVIEW ones).
"""

from modelforge.services.evidence.registry import EvidenceRegistry

__all__ = ["EvidenceRegistry"]
