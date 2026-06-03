# Emergency Supply Network Design and Resilience (network / graph + flow)

**Category:** network / graph optimization

A regional relief agency operates a logistics network of 30 candidate nodes
(warehouses, transfer hubs, demand towns) connected by roads with travel times,
capacities, and per-unit transport costs. A dataset gives the edge list (with
time, capacity, cost), node demands/supplies, and a disruption-probability per
edge.

**Q1.** Model the network and compute baseline structure: shortest-time paths from
the two supply warehouses to all demand towns, and the most critical nodes/edges
(centrality) whose loss most degrades reachability.

**Q2.** Formulate and solve a minimum-cost flow that satisfies all town demands
within capacity, and report the bottleneck edges.

**Q3.** Resilience: after the single most-critical edge fails, re-optimize and
quantify the increase in unmet demand and cost. Then design a capacity-expansion
plan (limited budget) that maximizes worst-case served demand.

**Q4.** Sensitivity: how do the optimal routing and the resilience plan change as
disruption probabilities and the expansion budget vary?

**Deliverable.** A competition paper with assumptions, a symbol table, graph and
flow formulations with notation, validation against a naive routing baseline, a
sensitivity analysis over budget/disruption, network figures, result tables, and
a strengths/weaknesses discussion.
