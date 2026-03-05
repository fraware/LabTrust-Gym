# Coordination Benchmark Card (coord_scale / coord_risk)

This card defines the coordination evaluation suite for scientific review: scenario generation, scale configs, methods, risk injections, metrics, determinism guarantees, and explicit limitations.

## Scope

The coordination **tasks** are **coord_scale** (nominal conditions) and **coord_risk** (with one injection per run). Each study run is a **cell**: (scale_id, method_id, injection_id). coord_scale and coord_risk evaluate multi-agent coordination in the **blood sciences lane** (pathology lab): specimen reception, accessioning, pre-analytics, routine and STAT analytics, QC, critical result notification, release; multi-site transport with chain-of-custody. Terminology: [Glossary – Lab terminology](../reference/glossary.md#lab-terminology-hospital-lab-pathology-lab-blood-sciences-lab). Agents are driven by a single coordination method; the environment enforces RBAC, signatures, and invariants as for core tasks. This benchmark measures coordination quality (throughput, turnaround, violations, blocks) and optional security/robustness under injected risks.

## Scenario generation

- **Scale dimensions**: Defined in the coordination study spec as a Cartesian product (e.g. `num_agents`, `num_sites`, `num_devices`, `arrival_rate`, `horizon_steps`). Each combination yields a `CoordinationScaleConfig` passed to the benchmark runner.
- **Episode setup**: Per episode, the runner builds the PettingZoo Parallel env with the scale config, seeds the RNG with the cell seed (derived from `seed_base`, scale index, method index, injection index), and runs the coordination method (e.g. centralized planner, market auction, WHCA router) to produce per-agent actions. Specimen arrivals and device behavior are deterministic given the seed.
- **Risk injections**: coord_risk applies one injection per cell (e.g. INJ-COMMS-POISON-001, INJ-CLOCK-SKEW-001). Injections are policy-defined with optional intensity and seed_offset; the risk harness applies them deterministically.

## Scale configs

Scale configurations are defined in `policy/coordination/scale_configs.v0.1.yaml`. The study spec may use inline scales (Cartesian product of named dimensions) or reference named configs (e.g. `corridor_heavy`, `small_smoke`). Key knobs: `num_agents_total`, `role_mix`, `num_devices_per_type`, `num_sites`, `specimens_per_min`, `horizon_steps`, `timing_mode`.

| Config ID        | Description                                              |
|------------------|----------------------------------------------------------|
| corridor_heavy   | 200 agents, 2 sites, narrow corridors; routing stress.   |
| small_smoke      | 4 agents, 1 site; fast unit/smoke runs.                  |

(Additional configs from the policy registry are included at card generation time.)

## Methods

Coordination methods implement a common interface: `reset(seed, policy, scale_config)`, `propose_actions(obs, infos, t)`. Methods are registered in `policy/coordination/coordination_methods.v0.1.yaml` with `method_id`, `coordination_class`, `scaling_knobs`, `known_weaknesses` (risk_id), `required_controls`, `compatible_injections`. Examples: `kernel_centralized_edf`, `kernel_whca`, `kernel_auction_whca`, `centralized_planner`, `hierarchical_hub_rr`, `market_auction`, `gossip_consensus`, `swarm_reactive`, `consensus_paxos_lite`, `swarm_stigmergy_priority`, `marl_ppo`, `llm_constrained`. Risk coverage is in `policy/coordination/method_risk_matrix.v0.1.yaml`.

## Injections

Risk injections are listed in the coordination study spec and applied by the risk injection harness. Each entry has `injection_id`, optional `intensity`, and `seed_offset` for deterministic replay. Examples: INJ-COMMS-POISON-001, INJ-COMMS-DELAY-001, INJ-COMMS-DROP-001, INJ-COMMS-REORDER-001, INJ-CLOCK-SKEW-001, INJ-ID-SPOOF-001, INJ-DOS-PLANNER-001, INJ-COLLUSION-001, INJ-TOOL-MISPARAM-001, INJ-MEMORY-POISON-001, INJ-BID-SPOOF-001. The study spec defines the exact set and parameters used for a run.

## Metrics definitions

**Performance**

- **perf.throughput** (throughput_mean in summaries): Mean specimens completed per episode (or per step window) across episodes in the cell. Primary coordination quality signal; higher is better.
- **perf.p95_tat**: Mean of per-episode p95 turnaround time (seconds) across episodes; null if not available. Lower is better for latency-sensitive workflows.

**Safety**

- **safety.violations_total** (violations_mean in summaries): Sum of invariant violations across episodes in the cell. Lower is better; zero is target.
- **safety.blocks_total**: Sum of blocked actions (by reason code) across episodes. Distinguishes RBAC/token/signature blocks from invariant violations.

**Security (coord_risk)**

- **sec.attack_success_rate**: Fraction of episodes in the cell where the injected attack was deemed successful (when applicable). Lower is better; 0 when mitigations hold.
- **sec.stealth_success_rate_mean**: Fraction of episodes where the attack succeeded without timely detection (when applicable).
- **sec.detection_latency_steps**: Mean steps to first detection (when applicable).
- **sec.containment_time_steps**: Mean steps to containment (when applicable).

**Robustness and coordination**

- **robustness.resilience_score** (resilience_score_mean): Composite score from `policy/coordination/resilience_scoring.v0.1.yaml`: weighted sum of component scores (perf, safety, security, coordination). Each component is normalized to [0, 1]; weights sum to 1. Missing metrics use `missing_metric_behavior` (e.g. omit). Higher is better.
- **resilience.component_perf | safety | security | coordination**: Per-component scores used to compute resilience_score.
- **coordination.stale_action_rate**: Fraction of actions that were computed from stale view state (when blackboard/comms model is active). Lower is better.
- **coordination.route** (when WHCA): replan_rate, mean_plan_time_ms, deadlock_avoids.
- **coordination.alloc** (when auction): gini_work_distribution, mean_bid, rebid_rate.
- **coordination.llm_repair** (when repair-over-kernel): repair_call_count, repair_success_rate, repair_fallback_noop_count.

**Comms (when blackboard/comms model active)**

- **comm.msg_count**, **comm.p95_latency_ms**, **comm.drop_rate**: Message volume, p95 delivery latency, and drop rate. Used to compare centralized vs decentralized methods and to stress comms injections.

## Baselines for SOTA comparison

The scripted baseline (ScriptedOpsAgent, ScriptedRunnerAgent) is the reproducibility reference for deterministic runs; SOTA comparison uses the baselines listed below (kernel_scheduler_or, kernel_whca, market_auction, etc.). When comparing a new coordination method to "state of the art," the following baselines are meaningful and are included in the coordination study spec and Layer 1 sanity scripts:

- **kernel_whca**: Centralized allocation + EDF + WHCA* routing; reference for collision-free routing and scale. Official non-LLM baseline in `benchmarks/baseline_registry.v0.1.yaml` (kernel_scheduler_or_v0 for OR variant).
- **market_auction** / **kernel_auction_edf**: Market-based allocation; reference for distributed assignment and bid-based robustness (R-DATA-001, INJ-BID-SPOOF-001).
- **hierarchical_hub_rr** / **hierarchical_hub_local**: Hierarchical reference for hub-cell split and handoff protocol; comparison for comm.msg_count and handoff_fail_rate.
- **kernel_scheduler_or** / **kernel_scheduler_or_whca**: Operations-research baseline (rolling-horizon OR scheduler); reference for weighted tardiness and fairness.

For a new method, the study spec defines the exact baseline set per scale and risk cell. Layer 1 sanity uses a default list (e.g. kernel_whca, market_auction, ripple_effect, group_evolving_experience_sharing); full registry mode runs all methods. See `policy/coordination/coordination_study_spec.v0.1.yaml`.

Summary output: `summary_coord.csv` (one row per cell: method_id, scale_id, risk_id, injection_id, plus the metrics above). Pareto report: `pareto.md` (per-scale Pareto front on p95_tat, violations_total, resilience_score; robust winner by mean resilience across cells).

**SOTA and method-class report artifacts:** When the study or pack output is summarized (`summarize-coordination` or `build-lab-coordination-report`), the following are written under `summary/`:

- **sota_leaderboard.md**, **sota_leaderboard.csv** (main): Per-method aggregates of the key metrics above, plus throughput_std and resilience_score_std when multiple cells exist. When `pack_manifest.json` is present, the main leaderboard Markdown includes Run metadata (seed_base, git_sha) at the top.
- **sota_leaderboard_full.md**, **sota_leaderboard_full.csv**: All aggregated numeric columns (security detection/containment, and when source is summary_coord: comm, LLM economics). Use for detailed analysis.
- **method_class_comparison.md**, **method_class_comparison.csv**: Same metrics aggregated by coordination class (kernel_schedulers, centralized, ripple, auctions, llm, etc.), including blocks_mean and attack_success_rate_mean. See [Hospital lab key metrics](../benchmarks/hospital_lab_metrics.md).

## Throughput-focused comparison

For **throughput** as the primary metric (mean specimen releases per episode), use the **throughput_sla** task rather than the coordination pack. Example: `labtrust run-benchmark --task throughput_sla --num-episodes 10 --out <path>` (scripted baseline from the baseline registry). Use `labtrust run-summary --run <dir>` or `summarize-results` for throughput in the output. See [Throughput comparison](../benchmarks/throughput_comparison.md) for the full path and optional kernel coordination.

## Determinism guarantees

- **Cell seed**: For a given study spec, `cell_seed = seed_base + scale_idx * 10000 + method_idx * 100 + injection_idx`. Same `seed_base` and spec yield identical cell seeds and thus identical episode sequences and metrics (modulo environment implementation).
- **Policy fingerprint**: A digest of the coordination policy files (study spec, scale configs, methods, method_risk_matrix, resilience_scoring) is computed and recorded so that results can be tied to the exact policy set. See "Policy fingerprint" below.
- **Reproducibility claim**: With the same `seed_base`, same study spec, and same coordination policy fingerprint, re-running the coordination study produces the same `summary_coord.csv` content (row order and values), excluding any timestamps that may be added to the report layout. Determinism-report style runs (two runs with same args) should yield identical hashes for `summary_coord.csv` (after normalizing line endings).

## Wall-clock and LLM latency (first-class when available)

When runs produce timing or LLM metadata, the following are exposed for deployment and capacity planning:

- **Wall-clock:** `run_duration_wall_s` (per-run total), `wall_clock_s_episode_total` and `wall_clock_s_per_step_mean` in pack-level `live_evaluation_metadata.json` when pipeline mode is llm_live. Step timing (e.g. `step_ms_mean`, `step_ms_p95`) is recorded in results metadata when `LABTRUST_STEP_TIMING=1` or when `--always-step-timing` is set. When `always_record_step_timing` is true, `metadata.step_timing` and `metadata.run_duration_wall_s` are always present; this mode is for capacity planning and may affect determinism if metadata is included in hashes.
- **LLM latency:** Results metadata and pack-level `live_evaluation_metadata.json` include `mean_llm_latency_ms`, `p50_llm_latency_ms`, `p95_llm_latency_ms`; pack-level aggregates `llm_latency_ms_p50`, `llm_latency_ms_p95`, `llm_latency_ms_max` when multiple task results are present.

See `live_evaluation_metadata.json` and per-task `results.json` metadata in `baselines/results/`; `PACK_SUMMARY.md` lists these outputs. **Contract:** For any run that uses an LLM coordination method, results (and summary) include cost and latency columns (`cost.estimated_cost_usd`, `p95_llm_latency_ms`, etc.); null if not available.

## What this benchmark is NOT measuring

- **Real-time or wall-clock performance (when not recorded):** When step timing or run_duration_wall_s are not produced, timing remains logical steps (and optional simulated device times). When recorded, wall-clock and LLM latency are first-class (see above).
- **Human-in-the-loop or approval workflows**: Coordination methods produce actions that are executed by the engine; no human approval or interrupt is modeled. When an approval hook is set (e.g. via `--approval-hook` or scale config), proposed actions are transformed by the hook after propose_actions and before env.step; the benchmark does not define human behavior.
- **Full FHIR or terminology validation**: As in the core benchmark, export and validation are minimal/structural. The optional `validate-fhir --terminology <value_set_json>` checks coded elements (Observation.code, Observation.interpretation) against a value set; not part of the minimal benchmark contract.
- **Adversarial robustness beyond the injection set**: Only the configured injections (and their intensities) are applied; no black-box adversary search in the official benchmark. Adversary search (prompt space via `scripts/run_adversary_search_prompt.py --budget N`, and optionally action space) is an optional extension; official benchmark uses only the fixed injection set. See [Security attack suite – Adversary search](../risk-and-security/security_attack_suite.md#adversary-search-optional-extension).
- **Generalization to unseen scales or injection types**: Results apply to the specified scale grid and injection list; extrapolation is out of scope. Exploratory presets (`exploratory_scale`, `exploratory_injection` via `--matrix-preset`) add one extra scale or one extra injection for ad-hoc experiments; not part of the frozen card matrix. See [Generalization and limits](generalization_and_limits.md) for what was tested, what was not, and comparison with other benchmarks.

**Implemented optional extensions:** The `--always-step-timing` flag (and `always_record_step_timing` in the runner) always records wall-clock per step for capacity planning; when set, `metadata.step_timing` and `run_duration_wall_s` are present regardless of pipeline mode. Human-in-the-loop is supported via an approval hook (after propose_actions, before env.step); use `--approval-hook auto_approve` or pass a custom callback. Full FHIR terminology validation is available as `validate-fhir --bundle <path> --terminology <value_set_json>` (optional; not part of the minimal benchmark contract). Adversarial robustness beyond the fixed injection set is available as optional scripts: prompt space via `scripts/run_adversary_search_prompt.py --budget N`, and action space via `scripts/run_adversary_search_action.py`. Exploratory presets (`exploratory_scale`, `exploratory_injection`) add one extra scale or injection via `--matrix-preset`; results are for ad-hoc experiments and are not part of the frozen card matrix.

## Policy fingerprint

The coordination policy fingerprint is the SHA-256 (hex) of the concatenation of sorted file hashes (path relative to `policy/coordination/`, then SHA-256 of file content). Files included: `coordination_study_spec.v0.1.yaml`, `scale_configs.v0.1.yaml`, `coordination_methods.v0.1.yaml`, `method_risk_matrix.v0.1.yaml`, `resilience_scoring.v0.1.yaml`. This section is replaced at card generation time with the actual fingerprint and optional per-file hashes.

```
COORDINATION_POLICY_FINGERPRINT_TOKEN
```

**See also:** [LLM Coordination Protocol](../benchmarks/llm_coordination_protocol.md) (pipeline modes, typed proposal schema, shield/repair, security evaluation, reporting). Package-release paper_v0.1 also emits **COORDINATION_LLM_CARD.md** (LLM methods, backends, injection coverage, limitations).
