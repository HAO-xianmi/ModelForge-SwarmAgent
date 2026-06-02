"""Deterministic services (spec section 9).

These do the work that must be reproducible: ingestion, profiling, sandboxed
execution, experiment tracking, robustness, evidence, citations, compliance,
and export. They contain no LLM calls — given the same inputs they produce the
same outputs (spec 4.5).
"""
