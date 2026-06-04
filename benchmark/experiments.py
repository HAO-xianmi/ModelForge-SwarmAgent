"""Domain-specific experiment pipelines (Phase H, Slice 5).

Each pipeline RUNS a real computation (no placeholder metrics), deterministic
under ``seed``, writes ``metrics.json`` + a figure to ``outdir``, and returns the
metrics dict. The harness converts these real numbers into evidence-linked
EvidenceClaims, so every reported number traces to an executed artifact.

Inputs are synthesized deterministically (realistic ranges) so the benchmark is
self-contained and reproducible; the NUMBERS are genuinely computed.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _save(outdir: Path, metrics: dict, fig) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / "figure.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    (outdir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


# --------------------------------------------------------------------------- #
def run_forecasting(outdir: Path, seed: int = 42) -> dict:
    import pandas as pd
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    rng = np.random.default_rng(seed)
    n = 24 * 60  # 60 days hourly
    t = np.arange(n)
    y = (50 + 0.01 * t + 10 * np.sin(2 * np.pi * t / 24)
         + 5 * np.sin(2 * np.pi * t / (24 * 7)) + rng.normal(0, 3, n))
    df = pd.DataFrame({"y": y, "hour": t % 24, "dow": (t // 24) % 7})
    for lag in (1, 2, 24, 168):
        df[f"lag{lag}"] = df["y"].shift(lag)
    df = df.dropna().reset_index(drop=True)
    split = int(len(df) * 0.8)
    feats = [c for c in df.columns if c != "y"]
    model = HistGradientBoostingRegressor(random_state=seed).fit(
        df[feats][:split], df["y"][:split])
    pred = model.predict(df[feats][split:])
    yte = df["y"][split:]
    base_pred = df["y"].shift(24)[split:]  # seasonal-naive baseline
    metrics = {
        "r2": round(float(r2_score(yte, pred)), 4),
        "rmse": round(float(mean_squared_error(yte, pred) ** 0.5), 4),
        "mae": round(float(mean_absolute_error(yte, pred)), 4),
        "baseline_seasonal_naive_r2": round(float(r2_score(yte, base_pred)), 4),
        "n_test": int(len(yte)), "n_features": int(len(feats)),
    }
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(yte.to_numpy()[:168], label="actual")
    ax.plot(np.asarray(pred)[:168], label="forecast")
    ax.legend(); ax.set_title("Forecast vs actual (1 week)")
    return _save(outdir, metrics, fig)


def run_irrigation(outdir: Path, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    days = 31
    T = rng.normal(26, 4, days)
    RH = rng.uniform(45, 90, days)
    u2 = rng.uniform(1, 4, days)
    Rs = rng.uniform(18, 28, days)
    rain = rng.gamma(1.5, 3.0, days) * (rng.random(days) < 0.3)
    # FAO-56 Penman-Monteith ET0 (daily)
    es = 0.6108 * np.exp(17.27 * T / (T + 237.3))
    ea = es * RH / 100.0
    delta = 4098 * es / (T + 237.3) ** 2
    gamma = 0.000665 * 101.3
    Rn = 0.77 * Rs - 2.45
    ET0 = ((0.408 * delta * Rn + gamma * 900 / (T + 273) * u2 * (es - ea))
           / (delta + gamma * (1 + 0.34 * u2)))
    ETc = 1.1 * ET0  # crop coefficient
    irr_mm = np.maximum(0.0, ETc - 0.8 * rain)
    area = 10000.0  # 1 hectare, 1 mm over 1 m^2 = 1 L
    irr_L = irr_mm * area
    spacing = 15 * math.sqrt(2)
    n_side = math.ceil(100 / spacing) + 1
    n_spr = n_side * n_side
    peak = float(irr_L.max())
    cost = n_spr * (50 * 15 ** 1.2 + 0.1 * (peak / n_spr) ** 1.5)
    metrics = {
        "mean_ET0_mm_day": round(float(ET0.mean()), 4),
        "total_irrigation_L": round(float(irr_L.sum()), 1),
        "peak_daily_L": round(peak, 1),
        "irrigation_days": int((irr_mm > 0).sum()),
        "n_sprinklers": int(n_spr),
        "total_cost_yuan": round(float(cost), 1),
        "coverage_fraction": round(min(1.0, n_spr * math.pi * 15 ** 2 / 10000.0), 4),
    }
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.bar(range(days), irr_L, color="#2a9d8f")
    ax.set_title("Daily irrigation demand (L)"); ax.set_xlabel("day")
    return _save(outdir, metrics, fig)


def run_network(outdir: Path, seed: int = 42) -> dict:
    import networkx as nx

    rng = np.random.default_rng(seed)
    # Sparser graph so single-node failures create real bottlenecks (a dense
    # graph trivially routes around any node -> uninteresting resilience=1.0).
    G = nx.gnm_random_graph(18, 30, seed=seed, directed=True)
    for u, v in G.edges():
        G[u][v]["capacity"] = int(rng.integers(5, 20))
        G[u][v]["weight"] = int(rng.integers(1, 10))
    nodes = list(G.nodes())
    # Pick the s-t pair with the largest max-flow (a meaningful demand to disrupt).
    s, t, flow = nodes[0], nodes[-1], -1.0
    for a in nodes[:5]:
        for b in nodes[-5:]:
            if a != b and nx.has_path(G, a, b):
                f = nx.maximum_flow_value(G, a, b, capacity="capacity")
                if f > flow:
                    s, t, flow = a, b, f
    bc = nx.betweenness_centrality(G, weight="weight")
    top3 = sorted(bc, key=lambda k: bc[k], reverse=True)[:3]
    # Worst-case resilience over removing each top-critical node (not s/t).
    worst_flow, worst_node = flow, top3[0]
    for nd in top3:
        if nd in (s, t):
            continue
        G2 = G.copy()
        G2.remove_node(nd)
        f2 = (nx.maximum_flow_value(G2, s, t, capacity="capacity")
              if s in G2 and t in G2 and nx.has_path(G2, s, t) else 0.0)
        if f2 < worst_flow:
            worst_flow, worst_node = f2, nd
    resilience = float(worst_flow / flow) if flow else 0.0
    metrics = {
        "max_flow": round(float(flow), 2),
        "critical_node": int(worst_node),
        "max_betweenness": round(float(bc[top3[0]]), 4),
        "flow_after_critical_failure": round(float(worst_flow), 2),
        "resilience_ratio": round(resilience, 4),
        "flow_loss_pct": round(100.0 * (1.0 - resilience), 1),
        "n_nodes": int(G.number_of_nodes()), "n_edges": int(G.number_of_edges()),
    }
    deg = sorted(bc.values(), reverse=True)
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.bar(range(len(deg)), deg, color="#264653")
    ax.set_title("Node betweenness (criticality)")
    return _save(outdir, metrics, fig)


def run_topsis(outdir: Path, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    # Quality-separated alternatives (clear tiers) so the ranking is meaningful
    # and the top is genuinely robust — not a near-tie that flips under noise.
    M = np.abs(rng.normal(5, 1.2, (10, 5))) + 0.1
    M = M + np.linspace(2.0, 0.0, 10)[:, None]  # alternative 0 strongest
    p = M / M.sum(0)
    p = np.where(p == 0, 1e-12, p)
    e = -1.0 / np.log(len(M)) * (p * np.log(p)).sum(0)
    w = (1 - e) / (1 - e).sum()
    norm = M / np.sqrt((M ** 2).sum(0))
    wn = norm * w
    dp = np.sqrt(((wn - wn.max(0)) ** 2).sum(1))
    dn = np.sqrt(((wn - wn.min(0)) ** 2).sum(1))
    C = dn / (dp + dn)
    top = int(np.argmax(C))
    N, stable = 200, 0
    for _ in range(N):
        wp = w * (1 + rng.normal(0, 0.1, 5))
        wp = np.abs(wp) / np.abs(wp).sum()
        wn2 = norm * wp
        dp2 = np.sqrt(((wn2 - wn2.max(0)) ** 2).sum(1))
        dn2 = np.sqrt(((wn2 - wn2.min(0)) ** 2).sum(1))
        if int(np.argmax(dn2 / (dp2 + dn2))) == top:
            stable += 1
    metrics = {
        "top_closeness_coefficient": round(float(C.max()), 4),
        "top_alternative": top,
        "weight_entropy": round(float(-(w * np.log(w + 1e-12)).sum()), 4),
        "rank_stability_top_pct": round(100.0 * stable / N, 1),
        "n_alternatives": int(len(M)), "n_criteria": int(M.shape[1]),
    }
    fig, ax = plt.subplots(figsize=(7, 3))
    order = np.argsort(-C)
    ax.bar(range(len(C)), C[order], color="#e9c46a")
    ax.set_title("TOPSIS closeness coefficients (ranked)")
    return _save(outdir, metrics, fig)


_PIPELINES = {
    "forecasting": run_forecasting,
    "irrigation": run_irrigation,
    "network": run_network,
    "topsis_evaluation": run_topsis,
}


def run_experiment(category: str, outdir: Path, seed: int = 42) -> dict:
    """Run the domain experiment for a benchmark category; returns real metrics."""
    fn = _PIPELINES.get(category)
    if fn is None:
        return {}
    return fn(Path(outdir), seed)
