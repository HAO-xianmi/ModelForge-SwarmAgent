"""Slice 5: domain experiment pipelines produce REAL, reproducible numbers,
and the harness turns them into evidence-linked claims with real values."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from benchmark.experiments import run_experiment
from benchmark.generate import _claims_from_experiment

_CATS = ["forecasting", "irrigation", "network", "topsis_evaluation"]


@pytest.mark.parametrize("cat", _CATS)
def test_experiment_executes_and_writes_artifacts(cat: str):
    d = Path(tempfile.mkdtemp())
    m = run_experiment(cat, d)
    assert m, f"{cat} returned no metrics"
    assert (d / "metrics.json").exists() and (d / "figure.png").exists()


def test_forecasting_model_beats_baseline():
    m = run_experiment("forecasting", Path(tempfile.mkdtemp()))
    assert m["r2"] > m["baseline_seasonal_naive_r2"]  # real validation result
    assert 0.0 < m["r2"] <= 1.0 and m["rmse"] > 0


def test_irrigation_computes_penman_monteith_demand():
    m = run_experiment("irrigation", Path(tempfile.mkdtemp()))
    assert 1.0 < m["mean_ET0_mm_day"] < 15.0  # physically plausible ET0
    assert m["total_irrigation_L"] > 0 and m["n_sprinklers"] > 0


@pytest.mark.parametrize("cat", _CATS)
def test_experiments_are_reproducible(cat: str):
    a = run_experiment(cat, Path(tempfile.mkdtemp()), seed=7)
    b = run_experiment(cat, Path(tempfile.mkdtemp()), seed=7)
    assert a == b  # identical seed -> identical numbers


def test_claims_carry_real_numbers_and_evidence_links():
    claims = _claims_from_experiment("forecasting")
    assert claims
    assert all(c.artifact_ids for c in claims)  # evidence traceability
    # at least one claim states a concrete numeric result
    assert any("R2 = 0." in c.statement for c in claims)
    assert all(c.verification_status.value for c in claims)
