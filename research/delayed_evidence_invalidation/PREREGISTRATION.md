# Preregistration v0.1 — Delayed Evidence Invalidation and Scientific-State Recovery

**Registration status:** frozen before implementation of the new benchmark task and before inspection of primary comparative outcomes  
**Frozen on:** 2026-10-08  
**Repository base:** `fraware/LabTrust-Gym@7e361583fb3e8ca4f482b072f4ac190e30cc69a5`  
**Study branch:** `research/delayed-evidence-invalidation-v0`

## 1. Research question

A continuously adaptive laboratory repeatedly executes the loop

[
B_t ightarrow a_t ightarrow e_t ightarrow B_{t+1},
]

where (B_t) is scientific state, (a_t) is the next experiment, and (e_t) is newly generated evidence.

This study asks:

> When evidence (e_k), previously admitted and used to update scientific state, is invalidated only at a later time (	au>k), which downstream scientific objects remain valid, which require recomputation or qualification, and which recovery strategy best restores a trustworthy scientific state while preserving useful work?

The first experimental family uses delayed discovery of calibration drift in a simulated pH measurement process. Detection of loss of measurement control is treated as an external metrology event. The contribution under test begins after that event: propagation, classification, and recovery.

## 2. Prior-art boundary and non-novel components

The study does **not** claim novelty for:

- laboratory measurement assurance, check standards, control charts, or calibration-drift detection;
- scientific workflow provenance or generic dependency graphs;
- claim/evidence lineage;
- machine unlearning or the general observation that deleting stored data does not erase learned influence;
- downstream influence in sequential decision systems;
- robust Bayesian optimization under corrupted observations;
- dynamic safety cases or runtime assurance;
- laboratory device interoperability.

Relevant adjacent work includes NIST measurement-assurance practice; ASTM D6299/E3500 statistical quality-control practice; W3C PROV and scientific-workflow provenance; robust Bayesian optimisation under corruptions; machine unlearning; offline-bandit unlearning; 2026 work on downstream “influence echoes” in self-improving agent networks; dynamic safety assurance; and OPC UA LADS.

The prospective contribution is narrower:

> Scientific invalidation in an adaptive physical experiment creates semantically distinct dependency classes—measurement validity, physical/sample lineage, model update, claim support, and experiment-selection dependence. Recovery should reason over those classes separately instead of treating every descendant as equally invalid.

This statement is a hypothesis to test, not a priority claim.

## 3. Formal state

At experiment (t), define

[
S_t=(P_t,M_t,E_t,B_t,Pi_t),
]

where:

- (P_t): physical/sample state and retained-material inventory;
- (M_t): metrological state, including instrument identity, calibration state, and validity envelope;
- (E_t): admitted evidence and its validity status;
- (B_t): scientific model/belief state;
- (Pi_t): experiment-selection state/policy.

A campaign also maintains a typed directed influence graph

[
G_t=(V,mathcal E).
]

Nodes may represent samples, measurements, raw signals, calibration states, derived values, model versions, experiment decisions, executed experiments, and claims.

Frozen edge types for v0.1:

- `MEASURED_UNDER`: measurement depends on instrument/calibration state;
- `DERIVED_FROM`: derived scientific object depends computationally or analytically on another object;
- `UPDATES`: evidence contributed to a model/belief-state update;
- `SELECTED_BY`: experiment choice was produced by a model/policy state;
- `SUPPORTS`: evidence/model supports a scientific claim;
- `EXECUTED_ON`: action or measurement applies to a specific physical sample/material lineage.

No edge type may be added to improve the primary result after primary outcomes are inspected. New types require a versioned protocol revision or secondary analysis.

## 4. Evidence validity states

Each evidence object carries a time-dependent state

[
v_i(t)in
{
	exttt{provisional},
	exttt{admitted},
	exttt{quarantined},
	exttt{invalidated},
	exttt{superseded}
}.
]

An invalidation record is

[
I=(e_i,	au,r,s,mathcal D),
]

with discovery time (	au), reason (r), affected validity scope (s), and supporting invalidation evidence (mathcal D).

The primary implementation must distinguish:

### Validity closure

(C_V(e)): descendants whose warrant or numerical value depends on invalid evidence through `MEASURED_UNDER`, `DERIVED_FROM`, `UPDATES`, or `SUPPORTS`.

### Selection-influence closure

(C_Pi(e)): experiments or artifacts whose existence/selection depends on contaminated policy/model states through `SELECTED_BY`.

The two closures are evaluated separately.

## 5. Descendant classification

Every downstream object receives exactly one primary recovery disposition:

- `INVALID`: its own scientific warrant directly depends on invalid evidence and no registered repair is available;
- `RECOMPUTE`: its source evidence remains available in a form that supports deterministic or registered recomputation;
- `SELECTION_TAINTED`: its creation/selection was influenced by invalid scientific state, while its own physical execution or measurement remains independently admissible;
- `UNAFFECTED`: no material dependency on the invalidated evidence exists.

If more than one label appears applicable, severity order is:

[
	exttt{INVALID} >
	exttt{RECOMPUTE} >
	exttt{SELECTION_TAINTED} >
	exttt{UNAFFECTED}.
]

This rule is frozen for v0.1.

## 6. Experimental substrate

### 6.1 Instrument layer

Primary instrument semantics follow the open OPC UA LADS reference pH-meter simulator. The simulator exposes:

- a Nernst-equation signal model;
- temperature compensation;
- pH slope and offset;
- raw signal;
- calibration values and calibration methods;
- simulated deliberate slope/offset detuning.

The benchmark integration may reproduce these semantics in Python for deterministic offline runs. If the TypeScript LADS server is used directly, the study must record its commit and preserve the same benchmark-level state variables.

### 6.2 Scientific response surface

The first study uses a synthetic, deterministic formulation-response surface. This surface is intentionally a benchmark function, not a claim of chemical realism.

Input:

[
xin[0,1].
]

True property:

[
pH^*(x)=7.0+1.20sin(2pi x)+0.35cos(6pi x)+0.25x.
]

Scientific objective:

[
u(x)=-(pH^*(x)-7.40)^2.
]

Measurement noise is introduced only through the instrument model.

The benchmark must expose the latent (pH^*(x)) only to the hidden adjudicator, never to the optimizer or recovery policy.

### 6.3 Adaptive policy

Primary policy: Gaussian-process upper-confidence-bound Bayesian optimization.

If the repository lacks an acceptable GP implementation without adding a heavy core dependency, the benchmark may place the BO implementation behind a study-only optional dependency. The exact package/version and kernel are frozen before primary campaign execution.

A robust-BO comparator must be included. Preferred comparator: RCGP-UCB or the closest reproducible public implementation from Ezzerg, Bogunovic, and Knoblauch (ICML 2026). If exact reuse proves impractical, the deviation must be documented before results are inspected.

### 6.4 Campaign horizon

- total experiments: (T=240);
- initial non-adaptive design: 16 space-filling points;
- adaptive experiments: 224;
- one retained physical sample record per experiment;
- check-standard event every 20 experiment slots;
- primary reference check: pH 7.00 at fixed temperature.

The check-standard operations are instrumentation events and do not count toward the 240 scientific experiments.

## 7. Calibration-only pre-study

Before primary campaign generation, run a calibration-only noise characterization at pH 7.00 with no drift.

- readings: 1,000;
- fixed calibration-study seed: 20261008;
- result: (hatsigma_0), the baseline standard deviation of the reported pH measurement.

No adaptive scientific campaign data are included in this estimate.

All primary drift magnitudes are expressed relative to (hatsigma_0), so the protocol remains portable across simulator implementations.

## 8. Drift process

Primary failure: gradual offset drift.

For each campaign seed:

1. drift onset (k) is sampled uniformly from experiment indices 60 through 120 using a hidden failure RNG stream;
2. after onset, offset grows linearly;
3. drift rate is drawn from the frozen set
   [
   {0.075,0.125,0.200}hatsigma_0
   ]
   per scientific experiment;
4. the optimizer does not observe onset or drift parameters.

Secondary ablation: slope drift with matched standardized effect size.

No combined slope+offset result may replace the offset-drift primary result.

## 9. Measurement-control rule

At each scheduled check-standard event, obtain five repeated readings.

Let (ar y_c) be the mean check reading. Trigger an out-of-control event if

[
|ar y_c-7.00| > 3hatsigma_0/sqrt{5}.
]

The immediately preceding check event that satisfied the control rule is the last-known-in-control checkpoint.

Primary suspect interval:

[
(t_{mathrm{last good}},t_{mathrm{detect}}].
]

This deliberately conservative interval is supplied to recovery methods that do not estimate a more precise onset.

The hidden oracle retains the true onset for evaluation only.

## 10. Stored-sample assumption

Primary study assumes physical samples remain available and stable for remeasurement through the campaign horizon.

This assumption is explicit because it creates a scientifically meaningful recovery action: remeasure a previously generated sample after restoring instrument control.

Secondary ablation will impose sample expiry windows. No general claim about recoverability is permitted without reporting this ablation.

## 11. Recovery conditions

### B0 — no retroactive recovery

The control alarm affects future operation only. Previously admitted evidence and model state remain unchanged.

### B1 — provenance flagging

The suspect interval is marked in the execution record. No model reconstruction occurs.

### B2 — QC + discard + retrain

All pH observations in the conservative suspect interval are removed. The scientific model is retrained on retained observations. No stored sample is remeasured.

### B3 — QC + blanket remeasurement + retrain

All retained samples from the conservative suspect interval are remeasured after instrument recovery, then the model is rebuilt.

This is a deliberately strong recovery baseline.

### B4 — typed dependency-aware recovery

The influence graph classifies affected artifacts, invalidates or recomputes dependent objects, and selects stored samples for remeasurement under the same recovery budget used by the matched B3 budgeted condition.

B4 may use graph structure and model-state information available before hidden adjudication. It may not use true drift onset, true latent pH, or hidden labels.

### B5 — robust BO + B2 recovery

Robust BO operates during acquisition, followed by the same conservative discard/retrain procedure as B2 after control failure is detected.

This tests whether robustness during optimization makes the recovery layer unnecessary.

## 12. Recovery budgets

Two analyses are preregistered.

### Exact/upper-bound recovery

B3 remeasures the full suspect interval. B4 may also use the full interval. This establishes the best attainable recovery under retained-sample access.

### Budgeted recovery

Remeasurement budgets are:

[
bin{0.10,0.25,0.50}
]

of samples in the conservative suspect interval, rounded up.

For B3 budgeted recovery, sample selection is uniform random with a dedicated RNG stream.

For B4, the selection rule must be frozen before primary outcomes. The intended rule is greedy expected reduction in model-state discrepancy estimated from the observed model and influence graph. If implementation requires a different criterion, it must be versioned before outcome inspection.

## 13. Hidden clean counterfactual

For each campaign seed, run a clean campaign with identical initial design, policy hyperparameters, non-failure RNG stream, and no drift.

Because adaptive action sequences diverge after corruption, the clean campaign is not treated as a pointwise paired trajectory after divergence. It is used as an adjudication reference.

The latent response surface also permits direct evaluation against physical ground truth independently of the clean policy trajectory.

## 14. Primary outcomes

### O1 — post-recovery scientific-model error

On a fixed dense evaluation grid (mathcal X_{eval}), measure normalized integrated squared prediction error against (pH^*(x)).

Primary comparison: B4 versus B2 and B3.

### O2 — retained scientifically valid work

Fraction of valid physical experiments / revalidated measurements retained in the recovered campaign state.

### O3 — recovery cost

Count of remeasurements plus normalized computational reconstruction cost. Physical remeasurement count is reported separately and receives priority over compute in interpretation.

### O4 — validity-classification accuracy

Against hidden oracle dependencies, macro-F1 over `INVALID`, `RECOMPUTE`, `SELECTION_TAINTED`, and `UNAFFECTED`.

No model-performance result substitutes for failure to classify dependencies correctly.

## 15. Secondary outcomes

- detection latency from true drift onset to control alarm;
- cumulative optimization regret;
- number of invalid observations admitted before alarm;
- validity-closure size;
- selection-influence-closure size;
- policy-path divergence from clean reference;
- number of scientific claims requiring withdrawal/recomputation;
- wall-clock recovery time;
- sample remeasurement efficiency;
- false invalidation of unaffected artifacts.

The following programme constructs are exploratory until validated:

- validity contamination depth;
- selection influence depth;
- scientific-state recovery fidelity;
- scientific waste.

They must not be presented as established community metrics.

## 16. Primary hypotheses

### H1 — delayed invalidation has consequences beyond a QC alarm

B0/B1 retain materially higher post-recovery model error or unsupported downstream state than B2–B4.

### H2 — dependency semantics preserve useful science

At matched model-error tolerance, B4 retains more scientifically valid work or requires fewer remeasurements than full rollback / blanket recovery.

### H3 — robust acquisition does not eliminate retroactive recovery

B5 reduces sensitivity to corrupted observations but does not, by itself, resolve provenance/claim invalidation or recover the correct dependency state after a late control failure.

### H4 — selection dependence differs from validity dependence

There exist campaigns containing artifacts correctly classified as `SELECTION_TAINTED` but not `INVALID`.

Failure to produce such cases in the primary family weakens the central semantic claim and requires either a second failure family or narrowing of the paper.

## 17. Statistical design

Primary Monte Carlo unit: campaign seed.

Initial target: 200 seeds per drift-rate condition, for 600 campaigns per method before recovery-budget expansion.

All methods operate on the same campaign seed and hidden failure realization where their acquisition semantics permit paired comparison.

Primary uncertainty reporting:

- bootstrap 95% confidence intervals over campaign seeds;
- paired bootstrap differences where trajectories share the same pre-divergence seed;
- effect sizes alongside p-values;
- full empirical distributions for heavy-tailed outcomes.

No claim rests solely on statistical significance.

A calibration run with 20 seeds per condition is permitted solely to verify code, runtime, nondegenerate drift detection, and absence of ceiling/floor effects. Those seeds are permanently excluded from primary analysis.

Any sample-size change after the 20-seed calibration must be justified from runtime/variance estimates and frozen before primary results are inspected.

## 18. Ablations required before broad claims

1. slope drift instead of offset drift;
2. different check intervals: 10, 20, 40;
3. stored-sample expiry / unavailable sample recovery;
4. different BO acquisition policy;
5. different latent response surface;
6. graph-edge removal, one type at a time;
7. incorrect or incomplete dependency metadata;
8. false-positive QC alarm;
9. multiple separate invalidation events.

A paper may report fewer ablations only if its claims are narrowed accordingly.

## 19. Kill criteria

The richer architecture is not supported if any of the following survives adequate testing:

1. B2 (QC + discard + retrain) matches B4 on model error, retained valid work, and recovery cost within practically negligible differences.
2. B3 blanket recovery dominates B4 across the recovery Pareto frontier.
3. validity and selection closures collapse to the same set in realistic benchmark variants.
4. B4's advantage depends on hidden information unavailable to a deployed system.
5. the result disappears under a second latent response surface or slope-drift family.
6. results depend on benchmark-specific identifiers or hand-coded knowledge of the injected failure.
7. a simpler generic provenance traversal reproduces B4 behavior with equivalent effort and outputs.
8. the LADS-aligned benchmark semantics materially differ from the reference implementation in ways that drive the result.

A null result must be reported as a programme-narrowing result, not repaired by weakening baselines after inspection.

## 20. Reproducibility requirements

Every released run must record:

- repository commit;
- study-contract digest;
- dependency versions;
- Python version;
- seed streams;
- latent-surface version;
- instrument-model version;
- drift realization;
- check-standard observations;
- recovery method configuration;
- influence graph before and after invalidation;
- raw and derived metrics.

Primary figures and tables must rebuild from released run artifacts.

The existing LabTrust paper-claims regression and release-pack machinery should be reused where practical.

## 21. External-validity ladder

Claims are tiered.

### Tier S0 — benchmark semantics

The implementation behaves as registered inside the deterministic benchmark.

### Tier S1 — standards-aligned simulation

Results reproduce through the OPC UA LADS-compatible instrument semantics.

### Tier S2 — second failure family / second substrate

The recovery semantics transfer to a non-metrological invalidation mechanism or another open autonomous-lab stack.

### Tier S3 — real laboratory shadow evaluation

The system processes authentic run artifacts without controlling live scientific actions.

### Tier S4 — prospective bounded pilot

Recovery outputs influence a real laboratory workflow under an independently approved operating envelope.

The first paper should claim no higher tier than the evidence actually achieved.

## 22. Implementation ownership

- **LabTrust-Gym:** campaign simulator, hidden oracle, failures, stored samples, benchmark runner, metrics.
- **EnvAssure:** metrological/environment validity semantics and validity-envelope transitions.
- **Scientific Memory:** persistent claim/evidence/model dependency records and typed influence graph.
- **AKTA:** consumes scientific-state disposition when deciding whether future action is admissible.
- **VerifierLab:** adversarial/repair campaign methodology and comparative qualification.

No new repository is authorized by this preregistration.

## 23. Planned first paper claim

The aspirational claim to test is:

> Delayed invalidation in adaptive autonomous experimentation creates scientifically distinct validity and selection dependencies. A typed, dependency-aware recovery process can restore scientific state while preserving more legitimate experimental work than coarse rollback or provenance/QC alone.

This sentence is not a supported result until the registered comparisons succeed.
