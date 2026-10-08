# Protocol Amendment v0.1.3 — Optimizer and non-stationarity baselines

**Date:** 2026-10-08  
**Timing:** before implementation of any Bayesian-optimization policy and before inspection of any primary comparative recovery outcome  
**Builds on:** v0.1.2

## Reason for amendment

The primary failure family is gradual persistent metrological drift. RCGP-UCB is a strong robustness comparator for observation corruptions, but its published theory studies frequency-constrained corruptions that may have unbounded magnitude. Persistent drift is structurally different. Time-varying GP-bandit work instead addresses stale observations under non-stationarity using resetting, forgetting, or sliding windows.

To avoid overstating one robustness baseline, this amendment:

1. freezes the scalar objective supplied to all optimizers;
2. freezes a matched GP-UCB implementation profile;
3. retains an RCGP comparator using the authors' released implementation;
4. adds sliding-window GP-UCB as the primary non-stationarity comparator; and
5. separates recovery comparisons from acquisition-robustness comparisons.

No primary campaign/recovery outcome has been inspected.

## 1. Optimizer-visible objective

The optimizer never receives latent true pH or latent utility.

For policy-visible reported pH \(\widehat{pH}_t\), define the observed BO target

\[
y_t^{obs}
=
-(\widehat{pH}_t-7.40)^2.
\]

For hidden adjudication only, define

\[
y_t^{true}
=
-(pH_t^*-7.40)^2.
\]

All optimizer policies use \(y_t^{obs}\). Regret and clean-reference evaluation may use \(y_t^{true}\).

## 2. Shared UCB schedule

All GP-UCB-style policies use the released RCGP codebase's theory-guided exploration multiplier:

\[
\beta_t
=
\max\left(
1.0,
1.7\sqrt{2\log(t+2)}
\right),
\]

where \(t\) is the zero-based adaptive-BO iteration after the 16-point initial design.

In this study, \(\beta_t\) is the literal multiplier on posterior standard deviation:

\[
a_t(x)=\mu_t(x)+\beta_t\sigma_t(x).
\]

This matches the released code interface and is not presented as a re-derivation of the paper's theoretical confidence notation.

## 3. Shared acquisition maximization

To eliminate numerical-acquisition optimization as a confound, every primary one-dimensional GP-UCB-style policy evaluates its acquisition on the same deterministic grid:

- domain: \([0,1]\);
- grid points: 1001, including both endpoints;
- selection: first grid index attaining the maximum acquisition value.

The released RCGP repository uses BoTorch continuous acquisition optimization in its generic experiment runner. This study deliberately replaces only that search step with the matched deterministic grid across all compared GP policies. Accordingly, the RCGP condition is a released-RCGP-surrogate comparator with matched UCB acquisition, not a claim of bit-for-bit reproduction of every released experiment script.

## 4. Standard GP-UCB

Primary adaptive acquisition policy for B0–B4:

- Gaussian-process implementation: BoTorch `SingleTaskGP`;
- outcomes standardized at each refit;
- model hyperparameters fitted by exact marginal likelihood at every adaptive iteration;
- double precision;
- CPU reference execution;
- all currently admitted policy-visible observations used;
- UCB multiplier from Section 2;
- deterministic 1001-point acquisition grid.

Reference optimizer package versions for the frozen study environment:

- Python 3.12;
- torch 2.8.0;
- botorch 0.15.1;
- gpytorch 1.14;
- numpy 1.26.4;
- scipy 1.12.0.

These versions match the released RCGP repository lock where applicable.

A study-local environment lock must record transitive dependencies before primary execution.

## 5. RCGP comparator

Reference implementation:

- repository: `EZZERG/RCGP`;
- pinned commit: `68bd978dfe4de28aed02184efc64ea343cfa9afc`;
- package version metadata: 0.1.0;
- authors' released environment requires Python >=3.12,<3.13.

The repository has no root LICENSE file at the pinned commit. The study must not vendor or redistribute its source. Integration should occur through a separately obtained local checkout/environment or a clean-room implementation based on published mathematics only after an explicit review.

For the external released-code comparator, freeze:

- model factory: released `create_rcgp_model`;
- standardized outcomes: true;
- P-IMQ plateau width: 1.96 on the standardized outcome scale;
- P-IMQ shape parameter \(c=1.0\);
- plateau center: fixed zero center;
- likelihood noise: fitted;
- GP mean: fitted;
- fitting objective: weighted leave-one-out cross-validation (`wloo-cv`);
- optimizer: L-BFGS using the released default path;
- UCB multiplier: Section 2;
- acquisition search: matched 1001-point grid, not the released `optimize_acqf` routine.

The \(L=1.96,c=1\) choice is motivated by the paper's standardized-data discussion of simple manual P-IMQ settings. It is frozen before results and will not be tuned on this benchmark.

This comparator must be described as an empirical RCGP-based robustness baseline. Its published sublinear-regret guarantees are not assumed to apply to persistent calibration drift.

## 6. Sliding-window GP-UCB non-stationarity comparator

Add a non-stationarity baseline family:

- `SW-GP-UCB-20`
- `SW-GP-UCB-40`
- `SW-GP-UCB-80`

Each uses the same Standard GP-UCB model, fitting, UCB schedule, and acquisition grid as Section 4, but the surrogate is refitted using only the most recent \(w\) scientific observations.

All three windows are reported. No window is selected post hoc as the single representative result.

The sliding-window family is motivated by established time-varying GP-bandit work, where resetting/sliding-window/forgetting methods address stale observations in non-stationary environments.

## 7. Recovery versus acquisition comparisons

The primary recovery estimand isolates recovery semantics:

- B0, B1, B2, B3, and B4 all operate on the **same pre-alarm Standard GP-UCB campaign trace** for a given seed and drift realization.
- Their differences begin only after the registered invalidation/control event.

Acquisition-robustness controls generate different trajectories and are analyzed separately:

- B5: RCGP comparator + B2 recovery after alarm;
- B6-20/B6-40/B6-80: corresponding sliding-window GP-UCB policy + B2 recovery after alarm.

B5/B6 are not used as paired evidence that B4 has better recovery semantics, because their experiment-selection trajectories differ before the alarm.

## 8. Hyperparameter and RNG discipline

- No optimizer hyperparameter may be selected using primary outcome performance.
- Any implementation calibration required for numerical stability must use only excluded calibration seeds.
- Torch/NumPy seeds must be deterministically derived from the registered campaign seed and adaptive iteration.
- Model-fitting failures, numerical warnings, or fallback paths must be recorded as first-class run artifacts.
- Failed optimizer fits may not be silently rerun with a new seed.

## 9. Additional kill criterion

The richer scientific-state recovery claim is weakened if a strong non-stationarity policy (any fixed preregistered SW-GP-UCB window) combined with B2 recovery matches B4 on post-recovery scientific-state quality and retained valid work at lower total cost.

If that occurs, the paper should narrow the contribution to settings where delayed semantic invalidation remains consequential after non-stationarity-aware acquisition.

## 10. Additional sensitivity analysis

Before making optimizer-independent claims, repeat the main recovery comparison using at least one acquisition policy other than full-history GP-UCB.

The acquisition-policy sensitivity result is secondary to the B0–B4 same-trace recovery comparison.

## 11. Explicit exclusions

Dynamic BO variants that add time directly as a GP input are relevant adjacent methods and should be discussed. They are not added as a primary v0.1.3 baseline because implementation and temporal-kernel choices would introduce another hyperparameter family. Sliding-window GP-UCB provides a transparent preregistered non-stationarity control. A time-input DBO replication may be added later as a versioned external-validity analysis, never retroactively as a primary baseline.
