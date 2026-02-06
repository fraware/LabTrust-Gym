# Coordination Benchmark Card (TaskG / TaskH)

This card defines the coordination evaluation suite for scientific review: scenario generation, scale configs, methods, risk injections, metrics, determinism guarantees, and explicit limitations.

## Scope

TaskG_COORD_SCALE and TaskH_COORD_RISK evaluate multi-agent coordination in the Blood Sciences lane (specimen reception, accessioning, pre-analytics, routine and STAT analytics, QC, critical result notification, release; multi-site transport with chain-of-custody). Agents are driven by a single coordination method; the environment enforces RBAC, signatures, and invariants as for core tasks. This benchmark measures coordination quality (throughput, turnaround, violations, blocks) and optional security/robustness under injected risks.

## Scenario generation

- **Scale dimensions**: Defined in the coordination study spec as a Cartesian product (e.g. `num_agents`, `num_sites`, `num_devices`, `arrival_rate`, `horizon_steps`). Each combination yields a `CoordinationScaleConfig` passed to the benchmark runner.
- **Episode setup**: Per episode, the runner builds the PettingZoo Parallel env with the scale config, seeds the RNG with the cell seed (derived from `seed_base`, scale index, method index, injection index), and runs the coordination method (e.g. centralized planner, market auction, WHCA router) to produce per-agent actions. Specimen arrivals and device behavior are deterministic given the seed.
- **Risk injections**: TaskH applies one injection per cell (e.g. INJ-COMMS-POISON-001, INJ-CLOCK-SKEW-001). Injections are policy-defined with optional intensity and seed_offset; the risk harness applies them deterministically.

## Scale configs

Scale configurations are defined in `policy/coordination/scale_configs.v0.1.yaml`. The study spec may use inline scales (Cartesian product of named dimensions) or reference named configs (e.g. `corridor_heavy`, `small_smoke`). Key knobs: `num_agents_total`, `role_mix`, `num_devices_per_type`, `num_sites`, `specimens_per_min`, `horizon_steps`, `timing_mode`.

| Config ID        | Description                                              |
|------------------|----------------------------------------------------------|
| corridor_heavy   | 200 agents, 2 sites, narrow corridors; routing stress.   |
| small_smoke      | 4 agents, 1 site; fast unit/smoke runs.                  |

(Additional configs from the policy registry are included at card generation time.)

## Methods

Coordination methods implement a common interface: `reset(seed, policy, scale_config)`, `propose_actions(obs, infos, t)`. Methods are registered in `policy/coordination/coordination_methods.v0.1.yaml` with `method_id`, `coordination_class`, `scaling_knobs`, `known_weaknesses` (risk_id), `required_controls`, `compatible_injections`. Examples: `kernel_centralized_edf`, `kernel_whca`, `kernel_auction_whca`, `centralized_planner`, `hierarchical_hub_rr`, `market_auction`, `gossip_consensus`, `swarm_reactive`, `marl_ppo`, `llm_constrained`. Risk coverage is in `policy/coordination/method_risk_matrix.v0.1.yaml`.

## Injections

Risk injections are listed in the coordination study spec and applied by the risk injection harness. Each entry has `injection_id`, optional `intensity`, and `seed_offset` for deterministic replay. Examples: INJ-COMMS-POISON-001, INJ-COMMS-DELAY-001, INJ-COMMS-DROP-001, INJ-COMMS-REORDER-001, INJ-CLOCK-SKEW-001, INJ-ID-SPOOF-001, INJ-DOS-PLANNER-001, INJ-COLLUSION-001, INJ-TOOL-MISPARAM-001, INJ-MEMORY-POISON-001, INJ-BID-SPOOF-001. The study spec defines the exact set and parameters used for a run.

## Metrics definitions

- **perf.throughput**: Mean specimens completed per episode (or per step window) across episodes in the cell.
- **perf.p95_tat**: Mean of per-episode p95 turnaround time (seconds) across episodes; null if not available.
- **safety.violations_total**: Sum of invariant violations across episodes in the cell.
- **safety.blocks_total**: Sum of blocked actions (by reason code) across episodes.
- **sec.attack_success_rate**: Fraction of episodes in the cell where the injected attack was deemed successful (when applicable).
- **sec.detection_latency_steps**: Mean steps to first detection (when applicable).
- **sec.containment_time_steps**: Mean steps to containment (when applicable).
- **robustness.resilience_score**: Composite score from `policy/coordination/resilience_scoring.v0.1.yaml`: weighted sum of component scores (perf, safety, security, coordination). Each component is normalized to [0, 1]; weights sum to 1. Missing metrics use `missing_metric_behavior` (e.g. omit).
- **resilience.component_perf | safety | security | coordination**: Per-component scores used to compute resilience_score.
- **comm.msg_count**, **comm.p95_latency_ms**, **comm.drop_rate**: Optional comms metrics when the blackboard/comms model is active.

Summary output: `summary_coord.csv` (one row per cell: method_id, scale_id, risk_id, injection_id, plus the metrics above). Pareto report: `pareto.md` (per-scale Pareto front on p95_tat, violations_total, resilience_score; robust winner by mean resilience across cells).

## Determinism guarantees

- **Cell seed**: For a given study spec, `cell_seed = seed_base + scale_idx * 10000 + method_idx * 100 + injection_idx`. Same `seed_base` and spec yield identical cell seeds and thus identical episode sequences and metrics (modulo environment implementation).
- **Policy fingerprint**: A digest of the coordination policy files (study spec, scale configs, methods, method_risk_matrix, resilience_scoring) is computed and recorded so that results can be tied to the exact policy set. See "Policy fingerprint" below.
- **Reproducibility claim**: With the same `seed_base`, same study spec, and same coordination policy fingerprint, re-running the coordination study produces the same `summary_coord.csv` content (row order and values), excluding any timestamps that may be added to the report layout. Determinism-report style runs (two runs with same args) should yield identical hashes for `summary_coord.csv` (after normalizing line endings).

## What this benchmark is NOT measuring

- **Real-time or wall-clock performance**: Timing is logical steps (and optional simulated device times). The benchmark does not measure actual LLM API latency or planner CPU time as a first-class outcome (though metadata may record them).
- **Human-in-the-loop or approval workflows**: Coordination methods produce actions that are executed by the engine; no human approval or interrupt is modeled.
- **Full FHIR or terminology validation**: As in the core benchmark, export and validation are minimal/structural.
- **Adversarial robustness beyond the injection set**: Only the configured injections (and their intensities) are applied; no black-box adversary search.
- **Generalization to unseen scales or injection types**: Results apply to the specified scale grid and injection list; extrapolation is out of scope.

## Policy fingerprint

The coordination policy fingerprint is the SHA-256 (hex) of the concatenation of sorted file hashes (path relative to `policy/coordination/`, then SHA-256 of file content). Files included: `coordination_study_spec.v0.1.yaml`, `scale_configs.v0.1.yaml`, `coordination_methods.v0.1.yaml`, `method_risk_matrix.v0.1.yaml`, `resilience_scoring.v0.1.yaml`. This section is replaced at card generation time with the actual fingerprint and optional per-file hashes.

```
**Fingerprint (SHA-256):** `4b07969d79f98285fb14cba327e556ee51f00bc19dba9ff3523eb92c196dd014`

| File | SHA-256 |
|------|---------|
| `coordination_methods.v0.1.yaml` | `0061c79b8cc058c06c55f8c2524040269a882b8f6c986a138ad12e2a90f446fe` |
| `coordination_study_spec.v0.1.yaml` | `444fe7bfc81880ea0308a31dc340961d0f25423dc589b533888addd2d865c6ee` |
| `method_risk_matrix.v0.1.yaml` | `3e30b8d31ec40f77e8201c5fb2d44f601359efe3375d226057862053d114b45a` |
| `resilience_scoring.v0.1.yaml` | `92300e1434532c4bd29edc34943e2c07ff009672b4e8a9952a1caa538517b688` |
| `scale_configs.v0.1.yaml` | `64cc5ae6a04620850ab33fa9c98004380a36b3b9fc13c0a5cf8d764350f31ef8` |

```
