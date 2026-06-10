"""Prediction (regression) code template — a real runnable scikit-learn project.

Trains the selected model with a proper train/test split (no leakage), evaluates
RMSE/MAE/R2, and writes metrics.json + a prediction-vs-actual figure. Falls back
to a clearly-labeled synthetic dataset when no CSV is present so a pilot can
establish feasibility.
"""

from __future__ import annotations

PREDICTION_MAIN = '''
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODEL_KIND = "__MODEL_KIND__"


def load_dataset():
    path = find_csv()
    synthetic = False
    if path is None:
        synthetic = True
        n = 200
        X = np.random.rand(n, 3)
        y = 3.0 * X[:, 0] - 2.0 * X[:, 1] + 0.5 * X[:, 2] + np.random.randn(n) * 0.1
        df = pd.DataFrame(X, columns=["f0", "f1", "f2"])
        df["target"] = y
        return df, "target", synthetic
    df = pd.read_csv(path)
    # Heuristic target selection: a column named target/y/label, else last numeric.
    target = None
    for cand in ("target", "y", "label", "value"):
        if cand in df.columns:
            target = cand
            break
    numeric = df.select_dtypes(include="number")
    if target is None or target not in numeric.columns:
        target = numeric.columns[-1]
    return df, target, synthetic


def build_model():
    if MODEL_KIND == "random_forest":
        return RandomForestRegressor(n_estimators=100, random_state=SEED)
    if MODEL_KIND == "gradient_boosting":
        return HistGradientBoostingRegressor(random_state=SEED)
    return LinearRegression()


def main():
    df, target, synthetic = load_dataset()
    numeric = df.select_dtypes(include="number")
    features = [c for c in numeric.columns if c != target]
    if not features:
        raise SystemExit("no numeric feature columns available for prediction")
    X = numeric[features].replace([np.inf, -np.inf], np.nan)
    X = X.dropna(axis=1, how="all")
    if X.empty:
        raise SystemExit("no usable numeric feature columns available for prediction")
    X = X.fillna(X.median()).fillna(0.0)
    y = numeric[target].replace([np.inf, -np.inf], np.nan)
    valid = y.notna()
    X = X.loc[valid]
    y = y.loc[valid]
    if len(y) < 4:
        raise SystemExit("not enough non-missing target rows for prediction")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=SEED
    )
    model = build_model()
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
    mae = float(mean_absolute_error(y_test, preds))
    r2 = float(r2_score(y_test, preds))

    # Prediction-vs-actual figure.
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(y_test, preds, alpha=0.6)
    lo = float(min(y_test.min(), preds.min()))
    hi = float(max(y_test.max(), preds.max()))
    ax.plot([lo, hi], [lo, hi], "r--")
    ax.set_xlabel("actual")
    ax.set_ylabel("predicted")
    ax.set_title(f"{MODEL_KIND}: prediction vs actual")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "prediction_vs_actual.png", dpi=120)

    # Results table.
    pd.DataFrame(
        {"actual": y_test.to_numpy()[:50], "predicted": preds[:50]}
    ).to_csv(OUTPUT_DIR / "predictions.csv", index=False)

    write_metrics({
        "rmse": rmse,
        "mae": mae,
        "r2": r2,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "n_features": int(len(features)),
        "synthetic_data": 1 if synthetic else 0,
        "model_kind": 1,  # presence marker; string recorded in stdout
    })
    print(f"model={MODEL_KIND} rmse={rmse:.4f} mae={mae:.4f} r2={r2:.4f} "
          f"synthetic={synthetic}")


if __name__ == "__main__":
    main()
'''
