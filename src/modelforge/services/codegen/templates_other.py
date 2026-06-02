"""Runnable templates for optimization, graph, classification, clustering, and
evaluation problem families. Each writes metrics.json + at least one figure/table
and is deterministic under MODELFORGE_SEED.
"""

from __future__ import annotations

OPTIMIZATION_MAIN = '''
import pandas as pd
import pulp
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_problem():
    """Load an allocation problem from CSV, or synthesize one.

    Expected CSV schema (flexible): columns including a 'value'/'profit' and a
    'cost'/'weight'; each row is an item. A single 'capacity' may be encoded in a
    column of the same name; otherwise a default capacity is used.
    """
    path = find_csv()
    if path is None:
        n = 8
        values = np.random.randint(5, 30, n).astype(float)
        weights = np.random.randint(1, 10, n).astype(float)
        return values, weights, float(weights.sum() * 0.5), True
    df = pd.read_csv(path)
    value_col = next((c for c in ("value", "profit", "benefit") if c in df.columns), None)
    weight_col = next((c for c in ("cost", "weight", "resource") if c in df.columns), None)
    numeric = df.select_dtypes(include="number")
    if value_col is None:
        value_col = numeric.columns[0]
    if weight_col is None:
        weight_col = numeric.columns[min(1, numeric.shape[1] - 1)]
    values = numeric[value_col].fillna(0).to_numpy(dtype=float)
    weights = numeric[weight_col].fillna(0).to_numpy(dtype=float)
    capacity = float(weights.sum() * 0.5)
    if "capacity" in df.columns:
        capacity = float(df["capacity"].dropna().iloc[0])
    return values, weights, capacity, False


def main():
    values, weights, capacity, synthetic = load_problem()
    n = len(values)
    prob = pulp.LpProblem("allocation", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x{i}", cat="Binary") for i in range(n)]
    prob += pulp.lpSum(values[i] * x[i] for i in range(n))
    prob += pulp.lpSum(weights[i] * x[i] for i in range(n)) <= capacity
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    chosen = [int(round(pulp.value(x[i]) or 0)) for i in range(n)]
    objective = float(pulp.value(prob.objective) or 0.0)
    used = float(sum(weights[i] * chosen[i] for i in range(n)))
    status = pulp.LpStatus[prob.status]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(range(n), values, color=["#2a9d8f" if c else "#cccccc" for c in chosen])
    ax.set_title("Allocation: selected items highlighted")
    ax.set_xlabel("item")
    ax.set_ylabel("value")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "allocation.png", dpi=120)

    pd.DataFrame(
        {"item": list(range(n)), "value": values, "weight": weights, "selected": chosen}
    ).to_csv(OUTPUT_DIR / "allocation.csv", index=False)

    write_metrics({
        "objective_value": objective,
        "capacity": capacity,
        "capacity_used": used,
        "n_items": n,
        "n_selected": int(sum(chosen)),
        "optimal": 1 if status == "Optimal" else 0,
        "synthetic_data": 1 if synthetic else 0,
    })
    print(f"status={status} objective={objective:.2f} used={used:.2f}/{capacity:.2f}")


if __name__ == "__main__":
    main()
'''


GRAPH_MAIN = '''
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ANALYSIS = "__ANALYSIS__"  # shortest_path | centrality | max_flow


def load_graph():
    path = find_csv()
    if path is None:
        g = nx.gnm_random_graph(12, 24, seed=SEED)
        for u, v in g.edges():
            g[u][v]["weight"] = float(np.random.randint(1, 10))
            g[u][v]["capacity"] = float(np.random.randint(1, 10))
        return g, True
    df = pd.read_csv(path)
    cols = [c.lower() for c in df.columns]
    df.columns = cols
    src = next((c for c in ("source", "src", "from", "u") if c in cols), cols[0])
    dst = next((c for c in ("target", "dst", "to", "v") if c in cols), cols[1])
    g = nx.Graph()
    for _, row in df.iterrows():
        w = float(row.get("weight", 1.0))
        cap = float(row.get("capacity", w))
        g.add_edge(row[src], row[dst], weight=w, capacity=cap)
    return g, False


def main():
    g, synthetic = load_graph()
    nodes = list(g.nodes())
    metrics = {"n_nodes": g.number_of_nodes(), "n_edges": g.number_of_edges(),
               "synthetic_data": 1 if synthetic else 0}

    if ANALYSIS == "centrality":
        bc = nx.betweenness_centrality(g, weight="weight")
        top = sorted(bc.items(), key=lambda kv: kv[1], reverse=True)[:10]
        pd.DataFrame(top, columns=["node", "betweenness"]).to_csv(
            OUTPUT_DIR / "centrality.csv", index=False)
        metrics["max_betweenness"] = float(max(bc.values())) if bc else 0.0
        labels = [str(t[0]) for t in top]
        vals = [t[1] for t in top]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(range(len(vals)), vals, color="#264653")
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
        ax.set_title("Top betweenness centrality")
        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / "centrality.png", dpi=120)
    elif ANALYSIS == "max_flow":
        dg = nx.DiGraph()
        for u, v, d in g.edges(data=True):
            dg.add_edge(u, v, capacity=d.get("capacity", 1.0))
            dg.add_edge(v, u, capacity=d.get("capacity", 1.0))
        s, t = nodes[0], nodes[-1]
        flow_value, _ = nx.maximum_flow(dg, s, t)
        metrics["max_flow_value"] = float(flow_value)
        metrics["source"] = float(hash(str(s)) % 1000)
    else:  # shortest_path
        s, t = nodes[0], nodes[-1]
        try:
            length = nx.shortest_path_length(g, s, t, weight="weight")
            path = nx.shortest_path(g, s, t, weight="weight")
        except nx.NetworkXNoPath:
            length = float("inf")
            path = []
        metrics["path_length"] = float(length) if length != float("inf") else -1.0
        metrics["path_nodes"] = float(len(path))
        pd.DataFrame({"path": [str(p) for p in path]}).to_csv(
            OUTPUT_DIR / "shortest_path.csv", index=False)

    # Graph layout figure (small graphs only).
    if g.number_of_nodes() <= 60:
        fig, ax = plt.subplots(figsize=(6, 5))
        pos = nx.spring_layout(g, seed=SEED)
        nx.draw(g, pos, ax=ax, node_size=120, node_color="#e9c46a", with_labels=True)
        ax.set_title(f"Graph ({ANALYSIS})")
        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / "graph.png", dpi=120)

    write_metrics(metrics)
    print(f"analysis={ANALYSIS} {metrics}")


if __name__ == "__main__":
    main()
'''


CLASSIFICATION_MAIN = '''
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODEL_KIND = "__MODEL_KIND__"


def load_dataset():
    path = find_csv()
    if path is None:
        n = 200
        X = np.random.rand(n, 4)
        y = (X[:, 0] + X[:, 1] > 1.0).astype(int)
        df = pd.DataFrame(X, columns=[f"f{i}" for i in range(4)])
        df["target"] = y
        return df, "target", True
    df = pd.read_csv(path)
    target = next((c for c in ("target", "label", "class", "y") if c in df.columns), None)
    if target is None:
        target = df.columns[-1]
    return df, target, False


def build_model():
    if MODEL_KIND == "decision_tree":
        return DecisionTreeClassifier(random_state=SEED, max_depth=6)
    if MODEL_KIND == "random_forest":
        return RandomForestClassifier(n_estimators=100, random_state=SEED)
    return LogisticRegression(max_iter=1000)


def main():
    df, target, synthetic = load_dataset()
    y = df[target]
    numeric = df.select_dtypes(include="number")
    features = [c for c in numeric.columns if c != target]
    X = numeric[features].fillna(numeric[features].median())
    X = StandardScaler().fit_transform(X)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=SEED, stratify=y if y.nunique() > 1 else None
    )
    model = build_model()
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    acc = float(accuracy_score(y_test, preds))
    f1 = float(f1_score(y_test, preds, average="weighted", zero_division=0))

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(["accuracy", "f1"], [acc, f1], color="#2a9d8f")
    ax.set_ylim(0, 1)
    ax.set_title(f"{MODEL_KIND} classification metrics")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "classification_metrics.png", dpi=120)

    write_metrics({
        "accuracy": acc, "f1": f1, "n_classes": int(y.nunique()),
        "n_test": int(len(y_test)), "synthetic_data": 1 if synthetic else 0,
    })
    print(f"model={MODEL_KIND} accuracy={acc:.4f} f1={f1:.4f}")


if __name__ == "__main__":
    main()
'''


CLUSTERING_MAIN = '''
import pandas as pd
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODEL_KIND = "__MODEL_KIND__"


def load_dataset():
    path = find_csv()
    if path is None:
        a = np.random.randn(80, 2) + np.array([0, 0])
        b = np.random.randn(80, 2) + np.array([5, 5])
        X = np.vstack([a, b])
        return pd.DataFrame(X, columns=["x", "y"]), True
    df = pd.read_csv(path)
    return df.select_dtypes(include="number"), False


def main():
    df, synthetic = load_dataset()
    X = StandardScaler().fit_transform(df.fillna(df.median()))
    if MODEL_KIND == "dbscan":
        labels = DBSCAN(eps=0.6, min_samples=5).fit_predict(X)
    else:
        labels = KMeans(n_clusters=3, random_state=SEED, n_init=10).fit_predict(X)

    n_clusters = int(len(set(labels)) - (1 if -1 in labels else 0))
    sil = -1.0
    if n_clusters >= 2:
        try:
            sil = float(silhouette_score(X, labels))
        except ValueError:
            sil = -1.0

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(X[:, 0], X[:, 1], c=labels, cmap="viridis", s=18)
    ax.set_title(f"{MODEL_KIND} clusters")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "clusters.png", dpi=120)

    write_metrics({
        "silhouette": sil, "n_clusters": n_clusters,
        "n_samples": int(len(X)), "synthetic_data": 1 if synthetic else 0,
    })
    print(f"model={MODEL_KIND} clusters={n_clusters} silhouette={sil:.4f}")


if __name__ == "__main__":
    main()
'''


EVALUATION_MAIN = '''
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

METHOD = "__METHOD__"  # entropy_weight | topsis | pca


def load_matrix():
    path = find_csv()
    if path is None:
        m = np.abs(np.random.rand(6, 4)) + 0.1
        return pd.DataFrame(m, columns=[f"c{i}" for i in range(4)]), True
    df = pd.read_csv(path).select_dtypes(include="number")
    return df, False


def entropy_weight(mat):
    p = mat / mat.sum(axis=0)
    p = np.where(p == 0, 1e-12, p)
    k = 1.0 / np.log(len(mat))
    e = -k * (p * np.log(p)).sum(axis=0)
    d = 1 - e
    return d / d.sum()


def topsis(mat, weights):
    norm = mat / np.sqrt((mat ** 2).sum(axis=0))
    weighted = norm * weights
    ideal = weighted.max(axis=0)
    anti = weighted.min(axis=0)
    d_pos = np.sqrt(((weighted - ideal) ** 2).sum(axis=1))
    d_neg = np.sqrt(((weighted - anti) ** 2).sum(axis=1))
    return d_neg / (d_pos + d_neg + 1e-12)


def main():
    df, synthetic = load_matrix()
    mat = df.to_numpy(dtype=float)
    mat = np.where(np.isnan(mat), np.nanmean(mat), mat)
    metrics = {"n_alternatives": int(mat.shape[0]), "n_criteria": int(mat.shape[1]),
               "synthetic_data": 1 if synthetic else 0}

    if METHOD == "pca":
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler
        Z = StandardScaler().fit_transform(mat)
        pca = PCA(n_components=min(mat.shape[1], 3)).fit(Z)
        ratios = pca.explained_variance_ratio_
        metrics["explained_variance_pc1"] = float(ratios[0])
        metrics["explained_variance_total"] = float(ratios.sum())
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.bar(range(1, len(ratios) + 1), ratios, color="#e76f51")
        ax.set_title("PCA scree")
        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / "scree.png", dpi=120)
    else:
        weights = entropy_weight(mat)
        scores = topsis(mat, weights) if METHOD == "topsis" else (mat * weights).sum(axis=1)
        ranking = np.argsort(-scores)
        metrics["top_score"] = float(scores.max())
        metrics["weight_entropy"] = float(-(weights * np.log(weights + 1e-12)).sum())
        pd.DataFrame({"alternative": range(len(scores)), "score": scores}).to_csv(
            OUTPUT_DIR / "ranking.csv", index=False)
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.bar(range(len(scores)), scores[ranking], color="#e9c46a")
        ax.set_title(f"{METHOD} scores (ranked)")
        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / "ranking.png", dpi=120)

    write_metrics(metrics)
    print(f"method={METHOD} {metrics}")


if __name__ == "__main__":
    main()
'''
