"""Unit tests for the deterministic structural scorer.

Each detector is checked on an award-rich fixture vs a weak-poor one, and the
scorer is asserted to be reproducible (identical input -> identical output).
"""

from __future__ import annotations

from modelforge.services.evaluation.ingest import ingest_text
from modelforge.services.evaluation.structural import (
    extract_metrics,
    structural_dimension_scores,
)

AWARD_RICH = """# 农业灌溉系统优化

## 摘要
本文针对农业灌溉系统优化, 建立 XGBoost 预测模型与优化模型。

## 模型假设
- 假设一：农场地形平坦, 忽略水力损失。
- 假设二：土壤理化性质均匀。
- 假设三：储水罐只能放在边界。

## 符号说明
符号 说明: It 第 t 天的灌溉量; Vk(t) 储水罐水量。

## 问题重述
本文需要解决四个子问题: 预测、布局、调度、扩容。

## 问题一模型的建立与求解
建立 XGBoost 模型。\\begin{equation} ET_0 = \\frac{0.408 \\Delta (R_n-G)}{\\Delta} \\end{equation}
$$ R^2 = 1 - \\frac{\\sum (y_i-\\hat y_i)^2}{\\sum (y_i-\\bar y)^2} $$
表 1 超参数设置。图 1 特征重要性。
模型在测试集 R2 达到 0.9712, RMSE 为 0.0112, 5 折交叉验证 R2 为 0.8172。
对比基线多元线性回归 R2 仅 0.22, 本模型显著更优。

## 问题二模型的建立与求解
\\begin{equation} \\min C = C_{pipe} + C_{tank} \\end{equation}
表 2 成本。图 2 布局。

## 问题三模型的建立与求解
基于蒙特卡洛仿真的灵敏度分析: 应急储备比例随旱灾概率从 20% 增至 90%。
表 3 应急储备与旱灾概率关系。图 3 敏感性曲线。

## 问题四模型的建立与求解
多阶段序贯决策。图 4 系统瓶颈。表 4 灌溉安排。

## 模型评价
优势: 体系完整。劣势: 模型简化。

## 参考文献
[1] ALLEN R G. Crop evapotranspiration. FAO, 1998.
[2] CHEN T. XGBoost. 2016.
[3] RAWLINGS J B. Model predictive control. 2017.
[4] METROPOLIS N. Monte Carlo. 1953.
[5] FRIEDMAN J H. Gradient boosting. 2001.
"""

WEAK_POOR = """# Agricultural Irrigation System Optimization

## Abstract
This paper presents a novel method for improving model performance on benchmark
tasks through a combination of architectural innovations and training techniques.

## Introduction
This report presents an analysis of key findings from recent experiments.

## Methods
The optimization problem was formulated as a QUBO model. The selected model
achieved an objective value of 98.0925 matching the baseline of 98.0925.

## Results
The objective value exhibited a stable result across runs.
"""


def _doc(text: str):
    return ingest_text(text, paper_id="t")


def test_award_paper_detects_rich_structure():
    m = extract_metrics(_doc(AWARD_RICH))
    assert m.n_subproblems >= 4
    assert m.n_equations >= 4
    assert m.n_tables >= 4
    assert m.n_figures >= 4
    assert m.n_assumptions >= 3
    assert m.has_baseline
    assert m.has_sensitivity
    assert m.has_symbol_table
    assert m.has_cross_validation
    assert m.has_validation_metrics
    assert m.n_references >= 5
    assert m.section_completeness >= 0.85


def test_weak_paper_detects_poor_structure():
    m = extract_metrics(_doc(WEAK_POOR))
    assert m.n_subproblems == 0
    assert m.n_assumptions == 0
    assert not m.has_sensitivity
    assert not m.has_symbol_table
    assert not m.has_cross_validation
    assert m.n_references == 0
    # the boilerplate mentions "baseline" so has_baseline may be True; that is
    # fine — the *score* must still separate (asserted below).


def test_structural_scores_separate_award_from_weak():
    award = structural_dimension_scores(extract_metrics(_doc(AWARD_RICH)))
    weak = structural_dimension_scores(extract_metrics(_doc(WEAK_POOR)))
    award_total = sum(award.values()) / len(award)
    weak_total = sum(weak.values()) / len(weak)
    assert award_total >= 8.0
    assert weak_total <= 3.0
    assert award_total - weak_total >= 4.0


def test_structural_scoring_is_reproducible():
    doc = _doc(AWARD_RICH)
    first = structural_dimension_scores(extract_metrics(doc))
    second = structural_dimension_scores(extract_metrics(doc))
    assert first == second


def test_each_structural_dimension_present():
    scores = structural_dimension_scores(extract_metrics(_doc(AWARD_RICH)))
    for dim in (
        "decomposition",
        "modeling_depth",
        "assumptions",
        "validation",
        "sensitivity",
        "results",
        "writing",
    ):
        assert dim in scores
        assert 0.0 <= scores[dim] <= 10.0
