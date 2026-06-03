# Agricultural Irrigation System Optimization (optimization + prediction)

**Category:** optimization + prediction (multi-part)
**Source:** APMCM 2025 Problem A (adapted)

A square 1-hectare farm sits beside a river and grows sorghum, maize, and
soybean under the principle "use river water normally, stored water in drought."
Hourly meteorological data and daily 5cm soil-moisture (`5cm_SM`) are provided.

**Q1 (prediction).** Build a model relating `5cm_SM` to the meteorological
factors and predict the soil moisture for a given day's hourly readings.

**Q2 (optimization).** Using July 2021 data, design the irrigation layout
(sprinkler placement, pipe routing, water-tank capacity and position) that
minimizes total construction cost while keeping every crop alive (soil moisture
≥ 0.22), subject to engineering constraints: tanks only on field boundaries or
zone borders, sprinkler spacing ≥ 15 m, full-field coverage.

**Q3 (dynamic + stochastic).** Under drought the river supply drops to 80% of the
Q2 design flow. (1) Build a dynamic scheduling model that maximizes surviving and
normally-growing crop area. (2) Quantify the relationship between drought
probability and the required emergency-reserve fraction.

**Q4 (multi-period adaptation).** Assuming a 20-day maturation period, plan a
month-by-month irrigation schedule for May–July, evaluate whether the static Q2
system meets dynamic demand, and propose an optimized modification if it does not.

**Deliverable.** A competition paper: assumptions, symbol table, per-question
models with derivations, validation against a baseline, sensitivity analysis, an
irrigation schedule table, figures, and a strengths/weaknesses discussion.
