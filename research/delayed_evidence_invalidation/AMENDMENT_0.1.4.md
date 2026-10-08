# Protocol Amendment v0.1.4 — Influence-graph orientation and strong recovery baselines

**Date:** 2026-10-08  
**Timing:** before implementation of the typed influence graph or any recovery operator and before inspection of primary comparative recovery outcomes  
**Builds on:** v0.1.3

## Reason for amendment

Two ambiguities remained before B4 implementation:

1. the original edge labels described semantic relations but did not freeze a single graph orientation; and
2. provenance-aware selective recomputation and active remeasurement are stronger simple baselines than flag-only provenance or random sample recovery.

Scientific-workflow systems have long used dependency provenance for partial/smart reruns and selective recomputation. The study therefore must not attribute generic dependency-based recomputation to the proposed scientific-state semantics.

## 1. Global graph orientation

Every edge is stored in **influence direction**:

[
	ext{prerequisite/source} ightarrow 	ext{dependent/affected object}.
]

The frozen relation labels retain their names, but endpoint semantics are:

- `MEASURED_UNDER`: metrological state -> measurement;
- `DERIVED_FROM`: source artifact -> derived artifact;
- `UPDATES`: evidence or prior model state -> subsequent model state;
- `SELECTED_BY`: model/policy state -> selected experiment;
- `SUPPORTS`: evidence/model -> supported claim;
- `EXECUTED_ON`: executed experiment/action -> resulting physical/sample state.

For a measurement of a retained sample, sample -> measurement may use `DERIVED_FROM` at v0.1.4. No new edge class is added solely to improve primary results after outcome inspection.

The label names are relation identifiers; arrow direction is always the source-to-dependent convention above even where ordinary English would phrase the inverse relation more naturally.

## 2. Validity propagation

Define the validity-propagating edge set

[
E_V=
{
	exttt{MEASURED_UNDER},
	exttt{DERIVED_FROM},
	exttt{UPDATES},
	exttt{SUPPORTS},
	exttt{EXECUTED_ON}
}.
]

`SELECTED_BY` is intentionally excluded.

For invalidated or quarantined roots (R), the method-visible validity closure is the reachable set using only (E_V).

This encodes the central hypothesis that a contaminated scientific model can select a future experiment without automatically making the physical experiment or its resulting sample scientifically invalid.

## 3. Selection-influence propagation

Let (C_V) denote the validity closure.

The selection-influence frontier consists of targets of `SELECTED_BY` edges whose source model/policy node lies in (C_V).

From that frontier, selection influence propagates through all downstream influence edges, including later model updates and later selection edges.

An object is `SELECTION_TAINTED` only if:

1. it lies in the selection-influence closure; and
2. it is not already in the validity closure or assigned a stronger repair disposition.

This allows a physically valid measurement to be marked as having occurred on a decision path influenced by invalid evidence without declaring the measurement itself false.

## 4. Recovery disposition

Primary disposition severity remains:

[
	exttt{INVALID}>
	exttt{RECOMPUTE}>
	exttt{SELECTION_TAINTED}>
	exttt{UNAFFECTED}.
]

Operational meaning for the pH-drift family:

- an original measurement under invalid metrology is `INVALID`;
- a derived observed utility or model state that can be rebuilt after removing/replacing invalid inputs is `RECOMPUTE`;
- an experiment/sample selected by a contaminated model but physically executed correctly is `SELECTION_TAINTED`;
- a remeasurement after restored metrology creates a new measurement node; it does not mutate the old invalid measurement into a valid one.

Method-visible quarantine may be broader than hidden-oracle invalidity. Scoring compares method classifications against the hidden oracle without exposing oracle onset.

## 5. Strengthened B2 — provenance-selective recomputation

B2 is now explicitly:

**QC + conservative evidence invalidation + provenance-selective computational recomputation.**

After the alarm:

1. quarantine/discard suspect-interval pH measurements from the scientific model;
2. identify computational/model/claim descendants using ordinary dependency provenance;
3. recompute only affected computational objects;
4. retain unaffected computational artifacts;
5. perform no physical sample remeasurement.

This is a strong generic provenance baseline. Any B4 advantage must exceed ordinary selective recomputation.

## 6. Strengthened active-remeasurement baseline B3U

Add B3U for each preregistered physical remeasurement budget.

B3U performs:

1. the same conservative suspect-interval quarantine as B2;
2. fit the same registered GP model to remaining admitted safe measurements;
3. among retained physical samples in the suspect interval, choose remeasurement candidates sequentially by maximum posterior predictive variance at the sample's original (x);
4. after each remeasurement, refit before choosing the next candidate;
5. rebuild the model after the budget is exhausted.

Tie break: lowest original experiment index.

B3U uses no typed influence semantics beyond the ordinary suspect interval and retained-sample inventory.

This baseline tests whether any B4 benefit is simply active experimental design during recovery.

## 7. B4 budgeted remeasurement rule

The previously provisional phrase “greedy expected model-state discrepancy reduction” is replaced by a frozen operational rule.

B4:

1. computes method-visible validity and selection-influence closures;
2. identifies retained physical samples whose original measurement is quarantined/invalid while the physical sample itself remains remeasurable;
3. fits the same safe-data GP as B3U;
4. sequentially chooses eligible remeasurement candidates by maximum posterior predictive variance;
5. uses the same budget and tie break as B3U;
6. creates new remeasurement/evidence nodes and recomputes only graph-affected scientific objects.

Thus B3U and B4 share the active-selection heuristic. Their difference is typed dependency/recovery semantics, not a stronger sample-selection algorithm.

## 8. Interpretation gate for the first failure family

The metrological pH-drift family may legitimately yield B3U approximately equal to B4 on model recovery. Such a result would show that typed semantics add little in a single-layer retained-sample setting.

A broad paper claim that typed scientific-state semantics improve recovery efficiency requires at least one additional preregistered failure family with a **different minimal repair action**, such as:

- computational/analysis invalidation where raw measurement is reusable and recomputation is sufficient; or
- physical/sample invalidation where remeasurement of the same artifact is insufficient and re-execution is required.

The first family alone may establish the problem, metrics, graph semantics, and delayed-invalidation phenomenon, but it cannot by itself justify a cross-layer recovery-superiority claim.

## 9. Additional kill criterion

If a generic provenance-selective recomputation baseline plus the same active remeasurement heuristic reproduces B4's classifications and recovery decisions across multiple failure families with equivalent complexity, the typed scientific-state layer has not earned a distinct technical contribution.

## 10. Benchmark portability

All graph/recovery code must depend on typed nodes, edges, validity states, and repair capabilities rather than pH-specific identifiers, drift parameters, or experiment indices.

Failure-family-specific code may construct the graph and provide node capabilities; the recovery engine itself must remain domain-neutral.
