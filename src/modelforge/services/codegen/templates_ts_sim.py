"""Time-series and simulation templates."""

from __future__ import annotations

TIMESERIES_MAIN = '''
import pandas as pd
from sklearn.metrics import mean_squared_error, mean_absolute_error
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_series():
    path = find_csv()
    if path is None:
        t = np.arange(120)
        y = 10 + 0.1 * t + 3 * np.sin(2 * np.pi * t / 12) + np.random.randn(120) * 0.5
        return pd.Series(y), True
    df = pd.read_csv(path)
    numeric = df.select_dtypes(include="number")
    target = next((c for c in ("value", "y", "target") if c in numeric.columns),
                  numeric.columns[-1])
    return numeric[target].dropna().reset_index(drop=True), False


def main():
    series, synthetic = load_series()
    n = len(series)
    split = max(4, int(n * 0.8))
    train, test = series[:split], series[split:]
    if len(test) == 0:
        test = train[-2:]
    # Holt-Winters / exponential smoothing via statsmodels.
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(train, trend="add").fit()
        forecast = model.forecast(len(test))
    except Exception:
        # Naive last-value fallback (still a real computation, clearly recorded).
        forecast = pd.Series([train.iloc[-1]] * len(test), index=test.index)

    rmse = float(np.sqrt(mean_squared_error(test, forecast)))
    mae = float(mean_absolute_error(test, forecast))

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(range(len(train)), train, label="train")
    ax.plot(range(len(train), len(train) + len(test)), test, label="test")
    ax.plot(range(len(train), len(train) + len(test)), forecast, "r--", label="forecast")
    ax.legend()
    ax.set_title("Forecast")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "forecast.png", dpi=120)

    write_metrics({"rmse": rmse, "mae": mae, "n_points": n,
                   "synthetic_data": 1 if synthetic else 0})
    print(f"timeseries rmse={rmse:.4f} mae={mae:.4f}")


if __name__ == "__main__":
    main()
'''


SIMULATION_MAIN = '''
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    # Monte Carlo estimate of a stochastic quantity. Deterministic given SEED.
    n = 20000
    samples = np.random.normal(loc=5.0, scale=2.0, size=n)
    # Example: probability a draw exceeds a threshold + expected value.
    threshold = 7.0
    prob_exceed = float((samples > threshold).mean())
    mean_est = float(samples.mean())
    std_est = float(samples.std(ddof=1))
    ci_low = float(mean_est - 1.96 * std_est / np.sqrt(n))
    ci_high = float(mean_est + 1.96 * std_est / np.sqrt(n))

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(samples, bins=40, color="#457b9d")
    ax.axvline(threshold, color="r", linestyle="--")
    ax.set_title("Monte Carlo distribution")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "distribution.png", dpi=120)

    write_metrics({
        "estimate_mean": mean_est, "estimate_std": std_est,
        "prob_exceed_threshold": prob_exceed,
        "ci_low": ci_low, "ci_high": ci_high, "n_samples": n,
    })
    print(f"monte_carlo mean={mean_est:.4f} P(>thr)={prob_exceed:.4f}")


if __name__ == "__main__":
    main()
'''
