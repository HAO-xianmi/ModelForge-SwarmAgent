"""
APMCM 2025 C题: 基于Quantum Boosting的二分类模型
QBoost Solution — Problems 1, 2, 3

Self-contained: uses only numpy, sklearn, matplotlib (all available in
the modelforge science extras). No Kaiwu SDK required; simulated annealing
is implemented from scratch (logically equivalent to the SDK solver).
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from sklearn.datasets import load_iris
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.ensemble import AdaBoostClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report
from sklearn.tree import DecisionTreeClassifier
import warnings
warnings.filterwarnings("ignore")

np.random.seed(42)

print("=" * 70)
print("APMCM 2025 C题: Quantum Boosting (QBoost) 二分类模型")
print("=" * 70)

# ============================================================
# 问题 1: 数据预处理与弱分类器构建
# ============================================================
print("\n【问题1】数据预处理与弱分类器构建")
print("-" * 50)

# 1.1 加载数据 — 取 Setosa(0) 和 Versicolor(1)
iris = load_iris()
mask = iris.target < 2
X_raw = iris.data[mask]
y_raw = iris.target[mask]
# 转为 {-1, +1}
y = np.where(y_raw == 0, -1, 1)
N_total = len(y)
feature_names = ["萼片长度", "萼片宽度", "花瓣长度", "花瓣宽度"]
print(f"数据集: Iris (Setosa + Versicolor), 共 {N_total} 个样本, {X_raw.shape[1]} 个特征")
print(f"标签分布: Setosa(-1)={np.sum(y==-1)}, Versicolor(+1)={np.sum(y==1)}")

# 1.2 标准化
scaler = StandardScaler()
X = scaler.fit_transform(X_raw)
print("\n预处理步骤:")
print("  1. 选取前两类(Setosa, Versicolor), 标签映射: 0→-1, 1→+1")
print("  2. StandardScaler 标准化: x' = (x - μ) / σ")
print(f"     各特征均值: {scaler.mean_.round(3)}")
print(f"     各特征标准差: {scaler.scale_.round(3)}")

# 1.3 划分训练集/测试集
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
N_train = len(y_train)
N_test = len(y_test)
print(f"\n数据划分: 训练集 {N_train} 样本, 测试集 {N_test} 样本 (80/20, stratified)")

# 1.4 构建弱分类器 — 决策桩 (单特征阈值)
# 对每个特征取若干分位点作为阈值，每个(特征, 阈值, 极性)组合为一个弱分类器
M_target = 20  # 目标分类器数量

def build_weak_classifiers(X_tr, n_thresholds=5):
    """Generate decision stump classifiers from training data."""
    classifiers = []
    n_features = X_tr.shape[1]
    for feat_idx in range(n_features):
        col = X_tr[:, feat_idx]
        thresholds = np.percentile(col, np.linspace(10, 90, n_thresholds))
        for thr in thresholds:
            for polarity in [1, -1]:
                classifiers.append((feat_idx, thr, polarity))
    return classifiers

stumps = build_weak_classifiers(X_train, n_thresholds=5)
# 保留最多M_target个 (取准确率最高的)
def stump_predict(X, feat_idx, thr, polarity):
    return np.where(polarity * (X[:, feat_idx] - thr) >= 0, 1, -1)

# 计算每个弱分类器在训练集上的准确率并排序
stump_accs = []
for s in stumps:
    preds = stump_predict(X_train, *s)
    acc = accuracy_score(y_train, preds)
    stump_accs.append(acc)

# 取准确率最高的M_target个
sorted_idx = np.argsort(stump_accs)[::-1][:M_target]
selected_stumps = [stumps[i] for i in sorted_idx]
selected_accs = [stump_accs[i] for i in sorted_idx]
M = len(selected_stumps)

print(f"\n构建 M={M} 个弱分类器 (决策桩, 单特征阈值):")
print(f"{'索引':>4} {'特征':>6} {'阈值':>8} {'极性':>5} {'训练准确率':>10}")
print("-" * 42)
for j, (s, acc) in enumerate(zip(selected_stumps, selected_accs)):
    feat_idx, thr, polarity = s
    print(f"  {j+1:>2}  {feature_names[feat_idx]:>6}  {thr:>7.4f}  {polarity:>+4}   {acc:.4f}")

# 构造预测矩阵 H: shape (N_train, M), 元素 ∈ {-1, +1}
H_train = np.column_stack([
    stump_predict(X_train, *s) for s in selected_stumps
])
H_test = np.column_stack([
    stump_predict(X_test, *s) for s in selected_stumps
])

print(f"\n预测矩阵 H_train: shape={H_train.shape}  (N_train x M)")

# ============================================================
# 问题 2: QBoost QUBO建模
# ============================================================
print("\n\n【问题2】QBoost QUBO建模")
print("-" * 50)

# QBoost目标函数 (Neven et al., 2012):
#   min_{w ∈ {0,1}^M} (1/N) * ||y - (1/K) H w||^2 + λ * 1^T w
#
# 展开后 (令 λ 吸收归一化因子):
#   = (1/N^2) * w^T (H^T H) w - (2/N^2) * (H^T y)^T w + const + λ * 1^T w
#
# QUBO形式: min w^T Q w  (上三角矩阵)
# Q_{jj} = -(2/N^2)*(H^T y)_j + (1/N^2)*Q_{HH,jj} + λ
# Q_{jk} = (2/N^2)*Q_{HH,jk}  (j<k)

lambda_reg = 0.005  # 正则化系数 (控制选取的分类器数量; 设置较小以确保选取有效分类器)

print("QBoost目标函数:")
print("  min_{w∈{0,1}^M} (1/N²)||y·N - H·w||² + λ·Σw_j")
print("")
print("等价QUBO形式: min_w  w^T Q w")
print("")

# 构建 Q 矩阵
HtH = H_train.T @ H_train   # (M, M)
Hty = H_train.T @ y_train   # (M,)
N2 = N_train ** 2

Q = np.zeros((M, M))
for j in range(M):
    Q[j, j] = (HtH[j, j] / N2) - (2.0 * Hty[j] / N2) + lambda_reg
for j in range(M):
    for k in range(j+1, M):
        Q[j, k] = 2.0 * HtH[j, k] / N2

print(f"QUBO矩阵 Q: shape=({M}x{M})")
print(f"  Q_{{jj}} = (1/N²)*(H^T H)_{{jj}} - (2/N²)*(H^T y)_j + λ")
print(f"  Q_{{jk}} = (2/N²)*(H^T H)_{{jk}}  (j<k, 上三角)")
print(f"  λ = {lambda_reg} (正则化系数)")
print(f"\nQ矩阵对角线统计: min={Q.diagonal().min():.4f}, max={Q.diagonal().max():.4f}")
print(f"Q矩阵非对角统计: min={Q[np.triu_indices(M,1)].min():.4f}, max={Q[np.triu_indices(M,1)].max():.4f}")

def qubo_energy(w, Q):
    """Compute QUBO objective: w^T Q w."""
    return float(w @ Q @ w)

# ============================================================
# 问题 3: 模拟退火求解 + 模型评估
# ============================================================
print("\n\n【问题3】模拟退火求解与模型评估")
print("-" * 50)

def simulated_annealing_qubo(Q, n_iter=50000, T_init=2.0, T_final=0.01, seed=42):
    """Simulated annealing solver for QUBO minimization.

    Logically equivalent to Kaiwu SDK's simulated annealing solver.
    Bit-flip Metropolis-Hastings on binary variables.
    """
    rng = np.random.default_rng(seed)
    M = Q.shape[0]
    # Initialize randomly
    w = rng.integers(0, 2, size=M).astype(float)
    best_w = w.copy()
    best_energy = qubo_energy(w, Q)

    T_decay = (T_final / T_init) ** (1.0 / n_iter)
    T = T_init

    for step in range(n_iter):
        # Random bit flip
        flip_idx = rng.integers(M)
        w_new = w.copy()
        w_new[flip_idx] = 1.0 - w_new[flip_idx]

        delta_E = qubo_energy(w_new, Q) - qubo_energy(w, Q)
        if delta_E < 0 or rng.random() < np.exp(-delta_E / T):
            w = w_new
            current_energy = qubo_energy(w, Q)
            if current_energy < best_energy:
                best_energy = current_energy
                best_w = w.copy()
        T *= T_decay

    return best_w.astype(int), best_energy

print("使用模拟退火算法求解QUBO (等价于Kaiwu SDK模拟退火求解器)")
print("参数: n_iter=50000, T_init=2.0, T_final=0.01")

w_opt, energy_opt = simulated_annealing_qubo(Q, n_iter=50000, T_init=2.0, T_final=0.01)

selected_mask = w_opt == 1
n_selected = int(w_opt.sum())
print(f"\n最优解: 选取了 {n_selected}/{M} 个弱分类器")
print(f"QUBO最优能量: {energy_opt:.6f}")
print(f"\n所选弱分类器 (w_j=1):")
print(f"{'索引':>4} {'特征':>6} {'阈值':>8} {'极性':>5} {'训练准确率':>10}")
print("-" * 42)
for j, (s, acc, sel) in enumerate(zip(selected_stumps, selected_accs, selected_mask)):
    if sel:
        feat_idx, thr, polarity = s
        print(f"  {j+1:>2}  {feature_names[feat_idx]:>6}  {thr:>7.4f}  {polarity:>+4}   {acc:.4f}")

# 强分类器预测
def qboost_predict(H, w_opt):
    """Strong classifier: sign of weighted sum of selected weak classifiers."""
    n_sel = int(w_opt.sum())
    if n_sel == 0:
        return np.ones(H.shape[0], dtype=int)
    raw = H @ w_opt / n_sel
    return np.where(raw >= 0, 1, -1)

y_pred_train = qboost_predict(H_train, w_opt)
y_pred_test = qboost_predict(H_test, w_opt)

acc_train = accuracy_score(y_train, y_pred_train)
acc_test = accuracy_score(y_test, y_pred_test)
prec_test = precision_score(y_test, y_pred_test, pos_label=1)
rec_test = recall_score(y_test, y_pred_test, pos_label=1)
f1_test = f1_score(y_test, y_pred_test, pos_label=1)

print(f"\nQBoost 强分类器性能:")
print(f"  训练集准确率: {acc_train:.4f}")
print(f"  测试集准确率: {acc_test:.4f}")
print(f"  测试集精确率: {prec_test:.4f}")
print(f"  测试集召回率: {rec_test:.4f}")
print(f"  测试集F1分数: {f1_test:.4f}")

# AdaBoost基线
ada = AdaBoostClassifier(
    estimator=DecisionTreeClassifier(max_depth=1),
    n_estimators=20, random_state=42, algorithm="SAMME"
)
ada.fit(X_train, y_train)
y_ada_train = ada.predict(X_train)
y_ada_test = ada.predict(X_test)
acc_ada_train = accuracy_score(y_train, y_ada_train)
acc_ada_test = accuracy_score(y_test, y_ada_test)
f1_ada_test = f1_score(y_test, y_ada_test, pos_label=1)

print(f"\n【对比】AdaBoost基线 (20棵决策桩):")
print(f"  训练集准确率: {acc_ada_train:.4f}")
print(f"  测试集准确率: {acc_ada_test:.4f}")
print(f"  测试集F1分数: {f1_ada_test:.4f}")

print(f"\n性能汇总对比:")
print(f"{'方法':>12} {'训练准确率':>10} {'测试准确率':>10} {'测试F1':>8}")
print("-" * 46)
print(f"{'QBoost':>12}   {acc_train:.4f}     {acc_test:.4f}   {f1_test:.4f}")
print(f"{'AdaBoost':>12}   {acc_ada_train:.4f}     {acc_ada_test:.4f}   {f1_ada_test:.4f}")

# ============================================================
# 可视化
# ============================================================
print("\n生成可视化图表...")

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("APMCM 2025 C题: QBoost 二分类模型分析", fontsize=14, fontweight="bold")

# 图1: 弱分类器准确率分布
ax1 = axes[0, 0]
colors = ["#e74c3c" if w == 1 else "#95a5a6" for w in w_opt]
bars = ax1.bar(range(1, M+1), selected_accs, color=colors, edgecolor="white", linewidth=0.5)
ax1.axhline(0.5, color="black", linestyle="--", alpha=0.5, label="Random baseline (0.5)")
ax1.set_xlabel("弱分类器索引 j")
ax1.set_ylabel("训练集准确率")
ax1.set_title("弱分类器准确率分布\n(红色=已选入QBoost集成)")
ax1.legend(fontsize=8)
ax1.set_ylim(0.4, 1.05)
ax1.set_xticks(range(1, M+1))

# 图2: QUBO矩阵热力图
ax2 = axes[0, 1]
im = ax2.imshow(Q, cmap="RdBu_r", aspect="auto")
plt.colorbar(im, ax=ax2)
ax2.set_title("QUBO矩阵 Q (上三角)")
ax2.set_xlabel("弱分类器索引 k")
ax2.set_ylabel("弱分类器索引 j")
ax2.set_xticks(range(0, M, 2))
ax2.set_yticks(range(0, M, 2))
ax2.set_xticklabels(range(1, M+1, 2))
ax2.set_yticklabels(range(1, M+1, 2))

# 图3: PCA投影可视化分类结果
from sklearn.decomposition import PCA
pca = PCA(n_components=2)
X_2d = pca.fit_transform(X)
X_train_2d = pca.transform(X_train)
X_test_2d = pca.transform(X_test)
var_ratio = pca.explained_variance_ratio_

ax3 = axes[1, 0]
# 测试集预测结果
correct = y_pred_test == y_test
markers_test = ["o" if y == -1 else "^" for y in y_test]
for i, (x2d, correct_i, marker) in enumerate(zip(X_test_2d, correct, markers_test)):
    color = "#2ecc71" if correct_i else "#e74c3c"
    ax3.scatter(x2d[0], x2d[1], c=color, marker=marker, s=80, zorder=5, alpha=0.9)
# Train 背景点
for i, (x2d, yi) in enumerate(zip(X_train_2d, y_train)):
    marker = "o" if yi == -1 else "^"
    ax3.scatter(x2d[0], x2d[1], c="gray", marker=marker, s=30, alpha=0.3, zorder=2)

from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0],[0], marker="o", color="w", markerfacecolor="#2ecc71", markersize=8, label="测试集-正确(Setosa)"),
    Line2D([0],[0], marker="^", color="w", markerfacecolor="#2ecc71", markersize=8, label="测试集-正确(Versicolor)"),
    Line2D([0],[0], marker="o", color="w", markerfacecolor="#e74c3c", markersize=8, label="测试集-错误"),
]
ax3.legend(handles=legend_elements, fontsize=7, loc="best")
ax3.set_xlabel(f"PC1 ({var_ratio[0]:.1%})")
ax3.set_ylabel(f"PC2 ({var_ratio[1]:.1%})")
ax3.set_title("QBoost测试集分类结果 (PCA投影)")

# 图4: 性能指标对比条形图
ax4 = axes[1, 1]
metrics = ["训练准确率", "测试准确率", "测试F1"]
qboost_scores = [acc_train, acc_test, f1_test]
ada_scores = [acc_ada_train, acc_ada_test, f1_ada_test]
x = np.arange(len(metrics))
w_bar = 0.35
ax4.bar(x - w_bar/2, qboost_scores, w_bar, label="QBoost", color="#3498db", alpha=0.85)
ax4.bar(x + w_bar/2, ada_scores, w_bar, label="AdaBoost", color="#e67e22", alpha=0.85)
ax4.set_xticks(x)
ax4.set_xticklabels(metrics, fontsize=9)
ax4.set_ylabel("分数")
ax4.set_ylim(0.8, 1.05)
ax4.set_title("QBoost vs AdaBoost 性能对比")
ax4.legend()
for i, (qs, as_) in enumerate(zip(qboost_scores, ada_scores)):
    ax4.text(i - w_bar/2, qs + 0.005, f"{qs:.3f}", ha="center", fontsize=8)
    ax4.text(i + w_bar/2, as_ + 0.005, f"{as_:.3f}", ha="center", fontsize=8)

plt.tight_layout()
plt.savefig("qboost_results.png", dpi=120, bbox_inches="tight")
print("可视化已保存: qboost_results.png")

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 70)
print("汇总报告")
print("=" * 70)
print(f"""
问题1 结果:
  - 数据集: 100个样本, 4个特征, 标准化处理
  - 弱分类器: M={M}个决策桩(单特征阈值)
  - 训练集准确率范围: [{min(selected_accs):.3f}, {max(selected_accs):.3f}]

问题2 结果:
  - QUBO矩阵 Q ∈ R^({M}x{M}), 上三角稀疏结构
  - 正则化系数 λ={lambda_reg}
  - Q对角元: (1/N²)(H^TH)_{{jj}} - (2/N²)(H^Ty)_j + λ
  - Q非对角: (2/N²)(H^TH)_{{jk}} (j<k)

问题3 结果:
  - 模拟退火: 50000步, T: 2.0→0.01
  - 选取 {n_selected}/{M} 个弱分类器
  - QBoost测试准确率: {acc_test:.4f}
  - QBoost测试F1:     {f1_test:.4f}
  - AdaBoost测试准确率: {acc_ada_test:.4f} (基线对比)
""")
print("完成!")
