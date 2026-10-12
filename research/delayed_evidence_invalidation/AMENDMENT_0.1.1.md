# Protocol Amendment v0.1.1 — Drift onset versus scientific invalidity

**Date:** 2026-10-08  
**Timing:** before implementation of the campaign simulator and before inspection of any primary comparative outcome  
**Supersedes:** specific validity semantics in PREREGISTRATION v0.1 Sections 8, 9, 15, and 17 where “drift onset” could be read as equivalent to “scientific invalidity onset”

## Reason for amendment

Gradual physical drift and scientific invalidity are distinct events.

A measurement process may begin drifting while remaining inside an application-validity tolerance and while scheduled check standards still satisfy the registered control rule. Treating every observation after the first nonzero physical drift as invalid would make the registered suspect interval logically inconsistent: an “in-control” check could occur after physical drift began.

The correction below separates:

1. **physical drift onset** — the first experiment whose simulated instrument parameter differs from its baseline; and
2. **scientific invalidity onset** — the first experiment whose systematic measurement bias exceeds a predeclared application-validity tolerance.

This amendment changes no observed results and was made before the campaign implementation existed.

## Effective validity rule

Let the systematic pH reporting bias at experiment (t) be

[
b_{mathrm{sys}}(t)=
E[hat{pH}_tmid pH_t^*,M_t]-pH_t^*,
]

where the expectation removes zero-mean measurement noise while retaining the current metrological state.

For the primary v0.1.1 benchmark, define the application-validity tolerance

[
delta_{mathrm{app}} = 1.0,hatsigma_0.
]

The hidden oracle defines the **scientific invalidity onset**

[
k_{mathrm{invalid}}
=
min{tge k_{mathrm{drift}}:
|b_{mathrm{sys}}(t)|>delta_{mathrm{app}}}.
]

Evidence before (k_{mathrm{invalid}}) is not labelled invalid solely because nonzero drift has begun.

## Detection and suspect interval

The registered check-standard rule remains unchanged:

[
|ar y_c-7.00|>3hatsigma_0/sqrt{5}.
]

The operational suspect interval supplied to non-oracle recovery methods remains

[
(t_{mathrm{last in control}},t_{mathrm{detect}}].
]

It should be described as an **operational bracketing interval**, not as proof of the true physical drift onset.

Under the primary parameters, the application-validity tolerance is lower than the check-mean alarm threshold, so delayed invalidity is possible: measurements may become scientifically invalid before the next scheduled check declares the process out of control.

## Evaluation changes

Primary hidden-oracle validity labels use (k_{mathrm{invalid}}), not (k_{mathrm{drift}}).

Report both:

- physical-drift detection latency: (t_{mathrm{detect}}-k_{mathrm{drift}});
- scientific-invalidity detection latency: (t_{mathrm{detect}}-k_{mathrm{invalid}}).

The primary count of “invalid observations admitted before alarm” begins at (k_{mathrm{invalid}}).

Validity-classification accuracy is scored against invalidity labels derived from (delta_{mathrm{app}}).

Selection-influence tracing may begin from evidence labelled invalid under this rule; physical drift alone does not initiate invalidation propagation.

## Required sensitivity analysis

Before broad claims, repeat the primary comparison for:

[
delta_{mathrm{app}}/hatsigma_0 in {0.5,1.0,2.0}.
]

The 1.0 condition remains primary.

If the main conclusion depends qualitatively on the 1.0 choice, the paper must narrow the claim accordingly.

## Claim discipline

This benchmark tolerance is a study parameter, not a universal pH-metrology criterion and not a claim about acceptable error in any production laboratory.
