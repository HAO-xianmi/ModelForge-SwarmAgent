"""DebuggerAgent (spec 8.8).

Provides the ``DebuggerFn`` callable the ExperimentRunner uses in its bounded
debug loop. The debugger proposes MINIMAL fixes and MUST NOT disable validation,
hard-code metrics, or fabricate outputs.

Because the executable code is template-generated and validated, most failures
are environmental rather than logical. This debugger applies a small set of safe,
deterministic repairs (e.g. relaxing an optional import) and otherwise declines —
it never forces a green run by faking results.
"""

from __future__ import annotations

from collections.abc import Callable

from modelforge.agents.base import AgentContext, BaseAgent
from modelforge.common.ids import new_id
from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.experiment import CodeArtifact, DebugPatch, SandboxResult


class DebugDecision(MFBaseModel):
    can_fix: bool
    reason: str
    explanation: str = ""


class DebuggerAgent(BaseAgent[DebugDecision]):
    agent_key = "debugger"
    output_schema = DebugDecision

    def __init__(self, ctx: AgentContext) -> None:
        super().__init__(ctx)

    def as_callable(
        self,
    ) -> Callable[[CodeArtifact, SandboxResult, int], tuple[CodeArtifact, DebugPatch] | None]:
        """Return a DebuggerFn for ExperimentRunner.run(debugger=...)."""

        def _debug(
            code: CodeArtifact, result: SandboxResult, attempt: int
        ) -> tuple[CodeArtifact, DebugPatch] | None:
            return self._safe_repair(code, result, attempt)

        return _debug

    def _safe_repair(
        self, code: CodeArtifact, result: SandboxResult, attempt: int
    ) -> tuple[CodeArtifact, DebugPatch] | None:
        stderr = result.stderr
        main = code.file("main.py")
        if main is None:
            return None

        # Safe deterministic repair: a missing optional dependency import that
        # the template can run without (e.g. statsmodels in the timeseries
        # template, which already has a numeric fallback). We comment out the
        # failing top-level import; the template's own fallback path handles it.
        # Only statsmodels is safe to disable (it has a numeric fallback in the
        # timeseries template). matplotlib is never disabled — figures are
        # evidence. We never fabricate a success.
        module = _missing_module(stderr) if "ModuleNotFoundError" in stderr else None
        if module == "statsmodels":
            patched_content = _comment_import(main.content, module)
            if patched_content != main.content:
                new_files = [
                    f.model_copy(update={"content": patched_content})
                    if f.filename == "main.py"
                    else f
                    for f in code.files
                ]
                new_code = code.model_copy(
                    update={"files": new_files, "code_artifact_id": new_id("code")}
                )
                return new_code, DebugPatch(
                    attempt=attempt,
                    reason=f"optional dependency '{module}' missing; using fallback path",
                    changed_files=["main.py"],
                    explanation="Commented the optional import; template fallback applies.",
                )
        # No safe minimal fix; decline (never fabricate a success).
        return None


def _missing_module(stderr: str) -> str | None:
    import re

    m = re.search(r"No module named '([^']+)'", stderr)
    return m.group(1).split(".")[0] if m else None


def _comment_import(content: str, module: str) -> str:
    lines = content.splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        if (
            stripped.startswith(("import " + module, "from " + module))
            and "try" not in stripped
        ):
            out.append("    # [debug] optional import disabled: " + stripped)
        else:
            out.append(line)
    return "\n".join(out)
