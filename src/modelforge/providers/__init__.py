"""Provider abstractions: LLM and (future) retrieval/sandbox providers.

The LLM layer is vendor-neutral (spec 3.4 non-goal: no single-provider lock-in).
A deterministic mock provider drives keyless CI and tests.
"""
