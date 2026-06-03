# Average-tier calibration: PENDING REAL SAMPLES

This tier is intentionally **empty**.

Per the design decision (2026-06-03), calibration uses **only real papers**. We do
NOT synthesize or degrade papers to fill this slot. The average tier holds
real, mid-tier competition papers (e.g. Successful Participant / 成功参赛奖 level,
or unranked-but-complete entries).

To add a sample:
1. Drop the extracted text as `benchmark/corpus/average/<slug>.txt`.
2. Add an entry to `benchmark/corpus/labels.json` with `"tier": "average"`.

No code change is required — datasets are discovered by file + label. The
harness skips this tier gracefully while it is empty, so development is not
blocked. The separation test asserts only over populated tiers.
