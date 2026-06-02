"""Compliance engine (spec 24).

Profile-driven, never a single hard-coded policy (spec 24.1). Loads a
:class:`CompetitionProfile` from YAML, decides allowed capabilities / required
checkpoints / restricted actions, and emits an AI-use disclosure document.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from modelforge.common.errors import PolicyViolationError
from modelforge.schemas.control import (
    CompetitionProfile,
    DisclosureInteraction,
    DisclosureRecord,
)

# competition_profiles/ lives at the repo root (spec 35 repo structure).
_PROFILES_DIR = Path(__file__).resolve().parents[4] / "competition_profiles"

_PROFILE_FILES = {
    "practice": "practice.yaml",
    "generic_contest": "generic_contest.yaml",
    "cumcm": "cumcm.yaml",
    "mcm_icm": "mcm_icm.yaml",
    "apmcm": "apmcm.yaml",
}


@lru_cache(maxsize=8)
def load_profile(name: str, profiles_dir: str | None = None) -> CompetitionProfile:
    """Load a profile by short name (e.g. ``practice``) or filename."""
    directory = Path(profiles_dir) if profiles_dir else _PROFILES_DIR
    filename = _PROFILE_FILES.get(name, name)
    if not filename.endswith((".yaml", ".yml")):
        filename = f"{filename}.yaml"
    path = directory / filename
    if not path.exists():
        raise PolicyViolationError(
            f"competition profile not found: {name}", context={"path": str(path)}
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _profile_from_yaml(raw)


def _profile_from_yaml(raw: dict) -> CompetitionProfile:
    caps = raw.get("allowed_capabilities", {})
    return CompetitionProfile(
        profile_id=raw.get("profile_id", "unknown"),
        competition_name=raw.get("competition_name", "Unknown"),
        rule_version=str(raw.get("rule_version", "1.0")),
        operating_mode=raw.get("mode", raw.get("operating_mode", "practice")),
        allowed_capabilities=dict(caps),
        prohibited_tools=list(raw.get("prohibited_tools", [])),
        required_checkpoints=list(raw.get("required_checkpoints", [])),
        required_disclosure_fields=list(raw.get("required_disclosure_fields", [])),
        restricted_actions=list(raw.get("restricted_actions", [])),
        notes=raw.get("notes", ""),
        source_reference=raw.get("source_reference", ""),
    )


class ComplianceEngine:
    """Enforces a loaded competition profile across a run (spec 24.3)."""

    def __init__(self, profile: CompetitionProfile) -> None:
        self.profile = profile

    # --- capability / action gates ------------------------------------ #
    def require_capability(self, capability: str) -> None:
        if not self.profile.capability_enabled(capability):
            raise PolicyViolationError(
                f"capability '{capability}' is disabled by profile "
                f"'{self.profile.profile_id}'",
                context={"capability": capability},
            )

    def capability_enabled(self, capability: str) -> bool:
        return self.profile.capability_enabled(capability)

    def check_action(self, action: str) -> None:
        if self.profile.action_restricted(action):
            raise PolicyViolationError(
                f"action '{action}' is restricted by profile '{self.profile.profile_id}'",
                context={"action": action},
            )

    def required_checkpoints(self) -> list[str]:
        return list(self.profile.required_checkpoints)

    def checkpoint_required(self, checkpoint_id: str) -> bool:
        return checkpoint_id in self.profile.required_checkpoints

    def disclosure_required(self) -> bool:
        return bool(self.profile.required_disclosure_fields) or (
            self.profile.operating_mode == "contest_compliant"
        )

    # --- disclosure document ------------------------------------------ #
    def build_disclosure(
        self, run_id: str, interactions: list[DisclosureInteraction]
    ) -> DisclosureRecord:
        return DisclosureRecord(run_id=run_id, interactions=interactions)

    def render_disclosure_markdown(self, record: DisclosureRecord) -> str:
        """Render the AI-use disclosure as Markdown (spec 24.4 / 28.3)."""
        lines = [
            "# AI-Use Disclosure",
            "",
            f"- **Run ID:** {record.run_id}",
            f"- **Competition:** {self.profile.competition_name} "
            f"(profile `{self.profile.profile_id}`, rules v{self.profile.rule_version})",
            f"- **Exported at:** {record.exported_at.isoformat()}",
            "",
            "This document discloses the AI tools used during this modeling "
            "workflow. The human user remains responsible for final submission "
            "decisions.",
            "",
            "## Interactions",
            "",
            "| Provider | Model | Purpose | Stage | Human edits | Human confirmed |",
            "|---|---|---|---|---|---|",
        ]
        for i in record.interactions:
            lines.append(
                f"| {i.provider} | {i.model_identifier} | {i.purpose} | {i.stage} "
                f"| {'yes' if i.human_edits else 'no'} "
                f"| {'yes' if i.human_confirmation else 'no'} |"
            )
        if not record.interactions:
            lines.append("| _none recorded_ | | | | | |")
        return "\n".join(lines) + "\n"
