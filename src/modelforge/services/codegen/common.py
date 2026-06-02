"""Shared code fragments used by every generated project.

Generated programs follow a strict contract:
  * read input data from ``../input``
  * write figures/tables to ``../output``
  * write a flat-or-nested numeric ``../output/metrics.json``
  * be deterministic given ``MODELFORGE_SEED``

The ``COMMON_HEADER`` is prepended to ``main.py`` so seeds are fixed and paths
are consistent across all templates.
"""

from __future__ import annotations

COMMON_HEADER = '''"""Auto-generated experiment entrypoint (ModelForge-Swarm).

Deterministic: seeds are fixed from MODELFORGE_SEED. Outputs are written under
../output, including metrics.json. No network access is performed.
"""
import json
import os
import random
from pathlib import Path

import numpy as np

SEED = int(os.environ.get("MODELFORGE_SEED", "42"))
random.seed(SEED)
np.random.seed(SEED)

INPUT_DIR = Path("../input")
OUTPUT_DIR = Path("../output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def write_metrics(metrics: dict) -> None:
    (OUTPUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))


def find_csv() -> Path | None:
    candidates = sorted(INPUT_DIR.glob("*.csv"))
    return candidates[0] if candidates else None
'''


# A tiny synthetic-data fallback so a pilot can run even when no dataset is
# provided. This produces REAL computed metrics on REAL (if synthetic) data —
# it is clearly labeled as synthetic in the metrics so it is never mistaken for
# a result on the user's data.
SYNTHETIC_NOTE = (
    "    # No dataset provided; generating a small synthetic dataset so the "
    "pilot can\n    # establish feasibility. Marked synthetic in metrics."
)
