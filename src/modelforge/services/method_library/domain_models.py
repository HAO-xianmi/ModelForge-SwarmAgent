"""Domain / mechanistic model registry + retrieval (Phase H, Slice 2).

Extensible knowledge base of domain-specific modeling patterns the RouteGenerator
retrieves from. Add a :class:`DomainModel` to ``DOMAIN_MODELS`` to extend it.
"""

from __future__ import annotations

from functools import lru_cache

from modelforge.schemas.enums import ProblemFamily
from modelforge.schemas.method_kb import DomainModel

P = ProblemFamily


def _m(**kw: object) -> DomainModel:
    return DomainModel(**kw)  # type: ignore[arg-type]


DOMAIN_MODELS: list[DomainModel] = [
    # ------------------------- mechanistic (water/agri) ------------------------ #
    _m(
        model_id="penman_monteith_et0",
        name="FAO-56 Penman-Monteith Reference Evapotranspiration",
        category="mechanistic",
        families=[P.PREDICTION, P.OPTIMIZATION, P.DIFFERENTIAL_EQUATIONS],
        summary="Physically-based reference evapotranspiration ET0 from energy "
        "balance + aerodynamics; the FAO standard for irrigation demand.",
        governing_equations=[
            r"ET_0 = \frac{0.408\,\Delta\,(R_n-G) + \gamma\,\frac{900}{T+273}\,u_2\,(e_s-e_a)}{\Delta + \gamma(1+0.34 u_2)}",
            r"e_s = 0.6108\,\exp\!\left(\frac{17.27 T}{T+237.3}\right)",
            r"ET_c = K_c \cdot ET_0",
        ],
        assumptions=["flat well-watered reference grass", "daily soil heat flux G≈0",
                     "wind speed at 2 m approximated from station anemometer height"],
        applicability=["irrigation water demand", "crop water requirement",
                       "any problem needing physically-grounded evaporation"],
        advantages=["internationally standardized", "needs only routine weather data",
                    "interpretable energy/aerodynamic split"],
        failure_modes=["bad radiation/wind data", "non-reference surfaces",
                       "sub-daily dynamics ignored"],
        validation_methods=["compare ET0 to lysimeter/pan estimates",
                            "sanity-check against seasonal norms"],
        sensitivity_methods=["vary Kc and net radiation Rn", "perturb wind speed u2"],
        implementation_hints=["compute Rn from latitude/altitude + Rs",
                              "derive psychrometric constant from pressure",
                              "aggregate hourly weather to daily means first"],
        typical_competition_usage="Q on irrigation/crop water demand; feeds a soil-"
        "water-balance to size tanks/pipes.",
        references=["Allen et al., FAO Irrigation & Drainage Paper 56 (1998)"],
        keywords=["evapotranspiration", "irrigation", "et0", "crop water", "weather", "penman"],
    ),
    _m(
        model_id="soil_water_balance",
        name="Soil Water Balance / Irrigation Requirement",
        category="mechanistic",
        families=[P.OPTIMIZATION, P.DIFFERENTIAL_EQUATIONS, P.PREDICTION],
        summary="Daily root-zone water balance: irrigation need = max(0, demand − "
        "effective rainfall) with a survival-threshold floor.",
        governing_equations=[
            r"I_t = \begin{cases}(0.22 - SM_t)\rho_{soil} d_{soil} & SM_t < 0.22\\ \max(0, ET_c - R_t) & \text{otherwise}\end{cases}",
            r"SM(x,y,t{+}1)=SM(x,y,t)+\frac{R(t)-ET(t)+I_{total}(x,y,t)}{V_{soil}\rho_w}",
        ],
        assumptions=["uniform soil properties", "fixed survival moisture threshold",
                     "negligible deep percolation/runoff at daily scale"],
        applicability=["irrigation scheduling", "tank/pipe sizing", "drought response"],
        advantages=["directly yields actionable irrigation volumes",
                    "couples cleanly to ET0 and to layout optimization"],
        failure_modes=["ignores lateral flow", "threshold mis-specification"],
        validation_methods=["mass-balance closure check", "compare to observed SM series"],
        sensitivity_methods=["vary survival threshold and soil depth",
                             "vary effective-rainfall fraction"],
        implementation_hints=["accumulate monthly demand for capacity sizing",
                              "track per-device contribution for coverage"],
        typical_competition_usage="Bridges prediction (Q1) and layout optimization (Q2).",
        references=["Allen et al., FAO-56 (1998)"],
        keywords=["soil moisture", "water balance", "irrigation requirement", "demand"],
    ),
    _m(
        model_id="mpc_rolling_horizon",
        name="Model Predictive Control (Rolling-Horizon Scheduling)",
        category="optimization",
        families=[P.OPTIMIZATION, P.SIMULATION, P.DIFFERENTIAL_EQUATIONS],
        summary="Receding-horizon optimal control: at each step optimize over an "
        "H-day forecast, execute the first action, then roll forward.",
        governing_equations=[
            r"\min_{u}\; J=\sum_{k=t}^{t+H-1}\!\iint (P_S\,\mathrm{dev}_S + P_G\,\mathrm{dev}_G)\,dx\,dy",
            r"\text{s.t. } \sum_j q_{s_j}(k)+\sum_k q_{rTk}(k) \le 0.8\,Q_{design}",
        ],
        assumptions=["reasonably accurate short-horizon forecast",
                     "convex-enough per-step subproblem", "priority weights encode goals"],
        applicability=["dynamic resource scheduling under constraints/disturbances",
                       "drought irrigation dispatch", "inventory/energy control"],
        advantages=["handles constraints + disturbances", "anticipatory",
                    "tunable survive-vs-grow trade-off via penalties"],
        failure_modes=["forecast error", "horizon too short", "infeasible step"],
        validation_methods=["closed-loop simulation over historical weather",
                            "compare to greedy/myopic policy"],
        sensitivity_methods=["vary horizon H and penalty weights PS/PG",
                             "vary supply-cut fraction"],
        implementation_hints=["warm-start each step from previous solution",
                              "discretize the field into coverage cells"],
        typical_competition_usage="Drought dynamic-scheduling sub-problem.",
        references=["Rawlings, Mayne & Diehl, Model Predictive Control (2017)"],
        keywords=["scheduling", "control", "drought", "dynamic", "rolling horizon", "dispatch"],
    ),
    _m(
        model_id="spatial_coverage_packing",
        name="Spatial Coverage / Geometric Packing Layout",
        category="optimization",
        families=[P.OPTIMIZATION, P.GRAPH],
        summary="Place facilities (sprinklers/tanks) to cover a region at minimum "
        "cost subject to spacing and siting constraints; greedy max-coverage or MILP.",
        governing_equations=[
            r"\min\; C_{total}=\sum_i (50 L_i^{1.2}+0.1 Q_i^{1.5})+\sum_j 5 V_j",
            r"\bigcup_i B(x_i,y_i,r)\supseteq \text{Field},\quad \lVert p_i-p_k\rVert\ge 15",
        ],
        assumptions=["circular coverage radius", "siting limited to boundaries/borders",
                     "cost separable into pipe + tank terms"],
        applicability=["facility location", "sensor/sprinkler placement", "coverage design"],
        advantages=["greedy gives fast near-optimal coverage", "MILP gives bounds"],
        failure_modes=["coverage gaps at corners", "greedy local optima"],
        validation_methods=["report coverage fraction", "check all constraints satisfied"],
        sensitivity_methods=["vary radius and spacing", "vary cost coefficients"],
        implementation_hints=["discretize candidate sites on a grid",
                              "iteratively add the site with max marginal new coverage"],
        typical_competition_usage="Minimum-cost layout sub-problem.",
        references=["Wolsey, Integer Programming (1998)"],
        keywords=["layout", "coverage", "placement", "facility location", "packing", "cost"],
    ),
    _m(
        model_id="markov_gamma_weather",
        name="Markov-Chain + Gamma Stochastic Weather Generator",
        category="stochastic",
        families=[P.SIMULATION],
        summary="Two-state wet/dry Markov chain for rain occurrence with Gamma-"
        "distributed rainfall amounts; drives Monte-Carlo risk analysis.",
        governing_equations=[
            r"P(\text{wet}_t\mid\text{wet}_{t-1})=p_{ww},\quad R_t\sim \mathrm{Gamma}(\alpha,\beta)",
            r"D_I=0.7\frac{\min(1,\max(0,\sum ET-\sum R))}{100}+0.3\frac{\min(1,\text{max dry run})}{31}",
        ],
        assumptions=["first-order Markov occurrence", "Gamma amount distribution",
                     "stationary parameters within a season"],
        applicability=["drought-risk simulation", "emergency-reserve sizing",
                       "any rainfall-driven uncertainty"],
        advantages=["captures persistence + skew of rainfall", "cheap to sample"],
        failure_modes=["non-stationarity", "underestimated extremes"],
        validation_methods=["match simulated wet-day fraction + amount moments to data"],
        sensitivity_methods=["vary drought probability and severity parameters"],
        implementation_hints=["fit transition probs + Gamma params from data",
                              "pair with Monte-Carlo over N=10^4 scenarios"],
        typical_competition_usage="Risk/reserve sub-problem (reserve % vs drought prob).",
        references=["Metropolis & Ulam, The Monte Carlo Method (1949)"],
        keywords=["drought", "risk", "rainfall", "monte carlo", "markov", "gamma", "reserve"],
    ),
    _m(
        model_id="multistage_stochastic_dp",
        name="Multi-Stage Sequential Decision / Stochastic DP",
        category="optimization",
        families=[P.OPTIMIZATION, P.SIMULATION],
        summary="Stage-wise decisions over a season with a dynamic drought index, "
        "evaluating static designs and triggering capacity expansion.",
        governing_equations=[
            r"W_{daily}(i,t)=\frac{W_{grow}+ET_0 k_{evap} f_{evap}-R_{eff}}{\eta_{irr} f_{eff}}",
            r"\text{utilization}=\frac{\max_t \sum_i W_{daily} A_i}{\min_t Q_{eff}(t)}",
        ],
        assumptions=["stagewise separability", "drought level from 7-day rainfall window"],
        applicability=["multi-period planning", "capacity adequacy", "expansion decisions"],
        advantages=["evaluates long-run adequacy", "quantifies bottlenecks + fixes"],
        failure_modes=["state-space explosion", "myopic if horizon too short"],
        validation_methods=["back-test utilization over the full season",
                            "verify expanded capacity meets peak demand"],
        sensitivity_methods=["vary drought-window threshold", "vary expansion budget"],
        implementation_hints=["compute monthly demand then peak-day utilization",
                              "compare tank-expansion vs new-pipe cost"],
        typical_competition_usage="Multi-month adaptation/bottleneck sub-problem.",
        references=["Bellman, Dynamic Programming (1957)"],
        keywords=["multi-stage", "sequential", "adaptation", "capacity", "bottleneck", "expansion"],
    ),
    # ------------------------------- evaluation -------------------------------- #
    _m(
        model_id="entropy_weight_topsis",
        name="Entropy-Weight + TOPSIS (objective MCDA)",
        category="hybrid",
        families=[P.EVALUATION],
        summary="Objective indicator weights from information entropy, combined with "
        "TOPSIS ranking by distance to ideal/anti-ideal solutions.",
        governing_equations=[
            r"w_j=\frac{1-e_j}{\sum_k(1-e_k)},\quad e_j=-\tfrac{1}{\ln n}\sum_i p_{ij}\ln p_{ij}",
            r"C_i=\frac{d_i^-}{d_i^+ + d_i^-}",
        ],
        assumptions=["criteria comparable after normalization", "monotone preference",
                     "benefit/cost direction known per criterion"],
        applicability=["multi-criteria ranking", "composite indices", "site/option selection"],
        advantages=["objective weights (no hand-tuning)", "full transparent ranking"],
        failure_modes=["rank reversal", "degenerate constant criteria",
                       "normalization sensitivity"],
        validation_methods=["check ranking stability", "compare to expert ranking if any"],
        sensitivity_methods=["perturb weights ±x%", "drop each indicator (leave-one-out)"],
        implementation_hints=["normalize benefit vs cost criteria separately",
                              "report the closeness coefficient and a ranked table"],
        typical_competition_usage="Evaluation/ranking problems; pair with a weight-"
        "sensitivity analysis.",
        references=["Hwang & Yoon, Multiple Attribute Decision Making (1981)",
                    "Shannon, A Mathematical Theory of Communication (1948)"],
        keywords=["evaluation", "ranking", "topsis", "entropy", "criteria", "mcda", "weight"],
    ),
    _m(
        model_id="rank_sensitivity_analysis",
        name="Weight / Indicator Rank-Sensitivity Analysis",
        category="hybrid",
        families=[P.EVALUATION, P.SIMULATION],
        summary="Quantify how a ranking moves under weight perturbation and "
        "leave-one-indicator-out, identifying robust vs unstable alternatives.",
        governing_equations=[
            r"\text{rank-stability}_i = 1 - \frac{\#\{\text{perturbations changing }rank_i\}}{N_{perturb}}",
        ],
        assumptions=["perturbation distribution is reasonable", "ranking model fixed"],
        applicability=["robustness of any MCDA ranking", "decision defensibility"],
        advantages=["turns a point ranking into a robust recommendation"],
        failure_modes=["too-narrow perturbation range hides instability"],
        validation_methods=["report stable top/bottom set across perturbations"],
        sensitivity_methods=["Monte-Carlo weight perturbation", "leave-one-out indicators"],
        implementation_hints=["sample weights on the simplex", "tabulate rank ranges"],
        typical_competition_usage="Mandatory sensitivity sub-question for evaluation.",
        references=["Saaty, decision making sensitivity literature"],
        keywords=["sensitivity", "robustness", "ranking", "perturbation", "evaluation"],
    ),
    # -------------------------------- network ---------------------------------- #
    _m(
        model_id="min_cost_flow",
        name="Minimum-Cost Flow / Transportation",
        category="network",
        families=[P.GRAPH, P.OPTIMIZATION],
        summary="Satisfy demands at minimum transport cost within edge capacities; "
        "LP/network-simplex solvable, exposes bottleneck edges.",
        governing_equations=[
            r"\min \sum_{(u,v)} c_{uv} f_{uv}\quad \text{s.t. } 0\le f_{uv}\le \kappa_{uv}",
            r"\sum_v f_{uv}-\sum_v f_{vu}=b_u\ \forall u",
        ],
        assumptions=["linear costs", "single commodity", "known demands/supplies"],
        applicability=["logistics", "supply networks", "relief distribution"],
        advantages=["polynomial-time exact", "dual prices reveal bottlenecks"],
        failure_modes=["infeasible if demand > capacity", "multi-commodity needs extension"],
        validation_methods=["check flow conservation + capacity", "compare to naive routing"],
        sensitivity_methods=["vary capacities/demands", "edge-removal resilience"],
        implementation_hints=["use networkx min_cost_flow or PuLP",
                              "report saturated (bottleneck) edges"],
        typical_competition_usage="Network demand-satisfaction sub-problem.",
        references=["Ahuja, Magnanti & Orlin, Network Flows (1993)"],
        keywords=["network", "flow", "transportation", "logistics", "min cost", "bottleneck"],
    ),
    _m(
        model_id="network_resilience_centrality",
        name="Network Resilience via Criticality / Centrality",
        category="network",
        families=[P.GRAPH, P.SIMULATION],
        summary="Rank critical nodes/edges (betweenness) and quantify performance "
        "loss under failure to drive a budget-constrained hardening plan.",
        governing_equations=[
            r"g(v)=\sum_{s\ne t}\frac{\sigma_{st}(v)}{\sigma_{st}},\quad \text{Resilience}=1-\frac{\Delta\text{served}}{\text{served}_0}",
        ],
        assumptions=["failure model (edge/node removal) is representative"],
        applicability=["critical-infrastructure analysis", "robust network design"],
        advantages=["identifies where to invest", "quantifies worst-case degradation"],
        failure_modes=["centrality choice matters", "cascading effects ignored"],
        validation_methods=["re-optimize after worst failure; report unmet demand"],
        sensitivity_methods=["vary disruption probability + hardening budget"],
        implementation_hints=["betweenness for criticality", "re-solve flow post-failure"],
        typical_competition_usage="Network resilience/expansion sub-problem.",
        references=["Freeman, Centrality in Social Networks (1978)"],
        keywords=["network", "resilience", "centrality", "critical", "failure", "robustness"],
    ),
    # ------------------------------ forecasting -------------------------------- #
    _m(
        model_id="gbdt_feature_engineering",
        name="Gradient-Boosted Trees with Lag/Rolling Feature Engineering",
        category="data_driven",
        families=[P.PREDICTION, P.CLASSIFICATION],
        summary="XGBoost-style boosted trees over engineered lag, rolling-stat, and "
        "calendar features for nonlinear tabular/time-series prediction.",
        governing_equations=[
            r"\hat y=\sum_k f_k(x),\quad \mathrm{Obj}=\sum_i l(y_i,\hat y_i)+\sum_k\Omega(f_k)",
            r"\Omega(f)=\gamma T+\tfrac12\lambda\lVert w\rVert^2",
        ],
        assumptions=["informative engineered features", "i.i.d. residuals after features",
                     "enough history for lags/rolling windows"],
        applicability=["demand/soil-moisture/energy forecasting", "nonlinear tabular regression"],
        advantages=["captures nonlinearity + interactions", "feature importance",
                    "robust to mixed feature types"],
        failure_modes=["overfitting on small data", "extrapolation beyond training range",
                       "leakage from future-derived features"],
        validation_methods=["time-series split", "k-fold CV", "report test-vs-CV gap honestly"],
        sensitivity_methods=["vary training-window length + feature subsets",
                             "permutation feature importance"],
        implementation_hints=["build 1/2/3/7-day lags + rolling mean/std",
                              "encode wind direction with sin/cos", "never use future leakage"],
        typical_competition_usage="Prediction Q1 (e.g. soil moisture, demand).",
        references=["Chen & Guestrin, XGBoost (2016)", "Friedman, Gradient Boosting (2001)"],
        keywords=["forecast", "prediction", "xgboost", "gradient boosting", "feature", "lag", "rolling", "soil moisture"],
    ),
    _m(
        model_id="seasonal_decomposition_intervals",
        name="Seasonal Decomposition + Prediction Intervals",
        category="data_driven",
        families=[P.PREDICTION],
        summary="Decompose series into trend/seasonal/residual, model each, and "
        "produce calibrated prediction intervals with a seasonal-naive baseline.",
        governing_equations=[
            r"y_t = T_t + S_t + R_t,\quad \hat y_{t+h}\pm z_{1-\alpha/2}\,\hat\sigma_h",
        ],
        assumptions=["additive (or multiplicative) seasonality", "stable seasonal period"],
        applicability=["hourly/daily demand forecasting", "uncertainty quantification"],
        advantages=["interpretable components", "honest uncertainty bands",
                    "natural seasonal-naive baseline to beat"],
        failure_modes=["regime shifts", "holiday/heatwave anomalies"],
        validation_methods=["RMSE/MAE/MAPE vs seasonal-naive", "interval coverage check"],
        sensitivity_methods=["vary horizon + training window", "feature-subset ablation"],
        implementation_hints=["STL or calendar dummies for seasonality",
                              "report when the model fails (holidays/extremes)"],
        typical_competition_usage="Forecasting Q with required baseline + intervals.",
        references=["Hyndman & Athanasopoulos, Forecasting: Principles & Practice"],
        keywords=["forecast", "seasonal", "time series", "prediction interval", "uncertainty", "demand"],
    ),
]


class DomainModelLibrary:
    def __init__(self, models: list[DomainModel] | None = None) -> None:
        self._models = models if models is not None else list(DOMAIN_MODELS)
        self._by_id = {m.model_id: m for m in self._models}

    def all(self) -> list[DomainModel]:
        return list(self._models)

    def get(self, model_id: str) -> DomainModel | None:
        return self._by_id.get(model_id)

    def retrieve(
        self,
        text: str,
        families: list[ProblemFamily] | None = None,
        *,
        top_k: int = 6,
    ) -> list[DomainModel]:
        """Rank domain models by family overlap + keyword surface in ``text``."""
        fam = set(families or [])
        t = text.lower()
        scored: list[tuple[float, DomainModel]] = []
        for m in self._models:
            score = 0.0
            if fam & set(m.families):
                score += 0.5
            hits = sum(1 for k in m.keywords if k in t)
            score += 0.5 * min(1.0, hits / 3.0)
            if score > 0:
                scored.append((score, m.model_copy(update={"suitability_score": round(score, 4)})))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [m for _, m in scored[:top_k]]


@lru_cache(maxsize=1)
def get_domain_model_library() -> DomainModelLibrary:
    return DomainModelLibrary()
