"""Workspace setup, static import inspection, and metrics collection.

Shared by both sandbox backends so the safety checks and the result-collection
logic are identical regardless of where code runs.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from modelforge.schemas.experiment import CodeArtifact


def prepare_workspace(workspace: Path, code: CodeArtifact, input_files: dict[str, bytes]) -> None:
    """Lay out the canonical sandbox workspace (spec 20.3).

    Writes source files into ``src/`` and input data into ``input/``. Output and
    logs directories are created empty for the code to populate.
    """
    for sub in ("input", "src", "output", "logs"):
        (workspace / sub).mkdir(parents=True, exist_ok=True)
    for f in code.files:
        (workspace / "src" / f.filename).write_text(f.content, encoding="utf-8")
    for name, data in input_files.items():
        safe = Path(name).name
        (workspace / "input" / safe).write_bytes(data)


def inspect_imports(src_dir: Path, allowed: frozenset[str]) -> list[str]:
    """Return a list of disallowed top-level imports found in the source.

    Static AST inspection (no execution). A non-empty result means the code
    should be POLICY_BLOCKED before it ever runs (defense in depth — the
    subprocess/container restrictions are the primary control).
    """
    violations: list[str] = []
    for py in sorted(src_dir.glob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=py.name)
        except SyntaxError:
            # Syntax errors are surfaced by execution, not the import check.
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in allowed:
                        violations.append(f"{py.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                if node.level == 0 and top and top not in allowed:
                    violations.append(f"{py.name}: from {node.module} import ...")
    return violations


def collect_metrics(output_dir: Path) -> dict[str, float]:
    """Parse ``output/metrics.json`` into a flat float dict.

    Metrics MUST be produced by the executed code; this only reads what the code
    wrote (working rule 5 — no fabricated metrics).
    """
    metrics_path = output_dir / "metrics.json"
    if not metrics_path.exists():
        return {}
    try:
        raw = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, float] = {}
    _flatten_numeric(raw, "", out)
    return out


def _flatten_numeric(obj: object, prefix: str, out: dict[str, float]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            _flatten_numeric(v, key, out)
    elif isinstance(obj, bool | int | float):
        out[prefix] = float(obj)
