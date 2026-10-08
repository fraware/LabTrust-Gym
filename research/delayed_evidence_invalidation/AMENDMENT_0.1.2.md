# Protocol Amendment v0.1.2 — Indexing, event ordering, drift sign, and false alarms

**Date:** 2026-10-08  
**Timing:** before implementation of the campaign simulator and before inspection of primary comparative outcomes  
**Builds on:** v0.1.1

This amendment freezes implementation degrees of freedom that were left implicit in v0.1/v0.1.1.

## Experiment indexing

Scientific experiments use **one-based** indices:

[
tin{1,ldots,240}.
]

The initial design occupies experiments 1–16. Adaptive selection begins at experiment 17.

The hidden physical-drift onset is sampled uniformly from the integer set

[
{60,ldots,120}.
]

The onset experiment itself receives the first nonzero drift increment.

## Check-standard ordering

A scheduled check-standard event occurs immediately **after** scientific experiments

[
20,40,60,ldots,240.
]

The check uses the same current instrument/metrological state as the scientific measurement just completed at that experiment index. It receives a separate measurement-noise draw.

Thus a check at experiment 80 summarizes instrument state after the 80th scientific experiment; it does not alter the scientific-experiment count.

## Primary drift direction

The primary offset-drift family uses positive physical offset drift:

[
Delta_{mathrm{offset}}(t)>0.
]

Under the LADS-aligned stale-calibration algebra this produces a negative systematic reported-pH bias.

A sign-reversal ablation with otherwise matched standardized magnitude is required before making sign-invariant claims.

## False-positive control alarms

A check-standard alarm before the hidden scientific-invalidity onset is a **false-positive control alarm** for purposes of this benchmark.

Such runs must:

1. remain in the released campaign corpus;
2. be counted in the false-alarm outcome;
3. never be silently regenerated with a different seed.

The primary delayed-invalidation recovery estimand is evaluated on campaigns in which scientific invalidity occurs before the first control alarm. This conditioning rule is fixed before results and must be reported with the unconditional alarm rate and the fraction of campaigns entering the primary recovery estimand.

A sensitivity analysis must also report all-seed operational cost so that a method is not rewarded for expensive reactions to false alarms.

## Additional required sensitivity analysis

Add:

- drift-sign reversal;
- false-positive alarm cost across all seeds.

No production-metrology claim follows from these benchmark choices.
