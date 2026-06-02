"""Code generation from runnable templates (spec 8.7 / 20.2).

The template library produces a multi-file Python project (load_data,
preprocess, model, evaluate, robustness, visualize, main) for a given problem
family. These are REAL programs that the sandbox executes to produce metrics and
figures — they are not LLM-authored prose. The CodeAuthorAgent (Phase E)
selects a template and parameterizes it; deterministic generation lives here so
tests do not depend on an LLM.
"""

from modelforge.services.codegen.generator import CodeGenerator

__all__ = ["CodeGenerator"]
