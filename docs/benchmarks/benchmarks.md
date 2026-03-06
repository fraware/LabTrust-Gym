# LabTrust-Gym Benchmarks

Benchmark harness for running multiple episodes with fixed seeds, recording metrics, and outputting JSON. The scripted baseline (ScriptedOpsAgent, ScriptedRunnerAgent) is the reproducibility reference; SOTA comparison is against the OR kernel, LLM coordination methods, and MARL as described in the [Coordination benchmark card](../coordination/coordination_benchmark_card.md).

## Tasks

### throughput_sla (Throughput under SLA)

- **Goal**: Throughput under SLA; routine load.
- **Initial state**: Deterministic from seed; 3–5 specimens at reception.
- **Episode length**: 80 steps.
- **Agents**: Scripted ops + scripted runners (ops_0, runner_0, runner_1).
- **Reward config**: `throughput_reward: 1.0`.
- **SLA**: 3600 s turnaround (accept→release) for on-time rate.

### stat_insertion (STAT under load)

- **Goal**: STAT specimens inserted under routine load; prioritization.
- **Initial state**: Deterministic from seed; 4–5 specimens.
- **Episode length**: 120 steps.
- **Agents**: Scripted ops + scripted runners.
- **Reward config**: `throughput_reward: 1.0`, `violation_penalty: 0.1`.
- **SLA**: 1800 s for on-time rate.

### qc_cascade (QC fail cascade)

- **Goal**: QC fail on one device; routing and cascade behavior.
- **Initial state**: Deterministic from seed; 2–3 specimens.
- **Episode length**: 100 steps.
- **Agents**: Scripted ops + scripted runners.
- **Reward config**: None (reward=0 initially).
- **SLA**: None.

### adversarial_disruption (Adversarial disruption)

- **Goal**: Detection, containment, and attribution under adversarial disruption.
- **Initial state**: Deterministic from seed; 3–4 specimens.
- **Episode length**: 80 steps.
- **Agents**: Scripted ops + scripted runners + **adversary_0** (deterministic adversarial policy).
- **Adversary behaviors**: Misroute racks (QUEUE_RUN to wrong device), attempt unauthorized restricted door, attempt expired token/replay, leave door open (no TICK mitigation).
- **Reward config**: throughput_reward 0.5, violation_penalty 0.2, blocked_penalty 0.1.
- **SLA**: 3600 s.
- **Metrics**: `detection_latency_s` (first violation ts − attack start), `containment_success` (enforcement before unsafe release), `attribution_confidence_proxy` (audit has agent_id + action chain).

### multi_site_stat (Multi-site STAT)

- **Goal**: Multi-site STAT: acute node STAT specimens, hub routine queue; transport latency; SLA + violations + critical comm compliance.
- **Initial state**: Deterministic from seed; 3–4 specimens.
- **Episode length**: 150 steps.
- **Agents**: Scripted ops + scripted runners (ops_0, runner_0, runner_1).
- **Reward config**: `throughput_reward: 1.0`, `violation_penalty: 0.1`.
- **SLA**: 2400 s turnaround.

### insider_key_misuse (Insider and key misuse)

- **Goal**: Trust skeleton under insider + key misuse: RBAC deny, forged signature, replay, revoked key, token misuse; measure containment and forensic quality.
- **Initial state**: Deterministic from seed; 2–3 specimens.
- **Episode length**: 50 steps.
- **Agents**: Scripted ops + runner_0 + **adversary_insider_0** (A_INSIDER_0 with limited RBAC).
- **Attack phases** (deterministic steps): (1) RELEASE_RESULT → RBAC_ACTION_DENY; (2) MOVE with forged signature → SIG_INVALID; (3) replay same signature → SIG_INVALID; (4) revoked key → SIG_KEY_REVOKED; (5) RELEASE_RESULT_OVERRIDE with fake token / token misuse → RBAC_ACTION_DENY or token blocked.
- **Reward config**: throughput_reward 0.3, violation_penalty 0.2, blocked_penalty 0.1.
- **Metrics**: `time_to_first_detected_security_violation`, `fraction_of_attacks_contained`, `forensic_quality_score` (receipts include signature + RBAC + token evidence).
- **Study sweep**: `policy/studies/study_spec.taskf_insider.v0.1.yaml` sweeps **strict_signatures** [false, true] to show effect on containment.

### coord_scale (Coordination at scale)

- **Goal**: Coordination at scale under nominal conditions; compare coordination methods (centralized, hierarchical, market, gossip, swarm, optional LLM).
- **Initial state**: Generated deterministically by scale config (num_agents, num_devices, num_sites, specimens_per_min, horizon_steps); see [Coordination scale](../coordination/coordination_scale.md).
- **Episode length**: From scale config `horizon_steps` (default 200).
- **Agents**: Scale-defined workers (A_WORKER_0001, …); coordination method proposes actions for all agents.
- **Reward config**: `throughput_reward`, `violation_penalty`.
- **CLI**: `labtrust run-benchmark --task coord_scale --coord-method <method_id> [--scale small_smoke|medium_stress_signed_bus|corridor_heavy] [--timing explicit|simulated] --episodes 1 --seed 42 --out results.json`.

### coord_risk (Coordination under risk)

- **Goal**: Coordination under injected risks; measure security and robustness (attack_success_rate, detection_latency, containment_time, resilience_score).
- **Initial state**: Same as coord_scale (scale config).
- **Episode length**: Same as coord_scale.
- **Agents**: Same as coord_scale; risk injector can mutate obs, messages, or actions (deterministic, auditable).
- **Injections**: Red-team injection sets are defined in `policy/coordination/injections.v0.2.yaml` (success_definition, detection_definition, containment_definition per set). Study spec references them via `policy/coordination/coordination_study_spec.v0.1.yaml` (e.g. INJ-COMMS-POISON-001, INJ-ID-SPOOF-001, INJ-COLLUSION-001). INJ-ID-SPOOF-001 must be blocked when strict signatures are enabled.
- **Red-team metrics** (coord_risk): In addition to `sec.attack_success_rate`, `sec.detection_latency_steps`, `sec.containment_time_steps`, the coordination study reports **sec.stealth_success_rate** (attacks that succeeded without detection), **sec.time_to_attribution_steps** (steps until attacker attribution), **sec.blast_radius_proxy** (scope of impact). Uncertainty: **sec.attack_success_rate_ci_lower/upper** (95% Clopper-Pearson), **sec.worst_case_attack_success_upper_95** (when 0 successes observed). See [Security attack suite](../risk-and-security/security_attack_suite.md) for red-team definitions and [Uncertainty quantification](uncertainty_quantification.md) for standard reporting.
- **CLI**: `labtrust run-benchmark --task coord_risk --coord-method <method_id> --injection <injection_id> [--scale small_smoke|medium_stress_signed_bus|corridor_heavy] [--timing explicit|simulated] --episodes 1 --seed 42 --out results.json`.
- **Study**: `labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out <dir>` produces per-cell results, summary_coord.csv, pareto.md, SOTA leaderboard, and method-class comparison. Aggregate with `labtrust summarize-coordination --in <dir> --out <dir>`. See [Coordination studies](../coordination/coordination_studies.md).
- **Coordination security pack** (internal regression): `labtrust run-coordination-security-pack --out <dir>` runs a fixed scale × method × injection matrix (deterministic, 1 ep/cell), writes pack_results/, pack_summary.csv, pack_gate.md. See [Security attack suite](../risk-and-security/security_attack_suite.md#coordination-security-pack-internal-regression).

### device_outage_surge — experimental

- **Goal**: Surge workload plus one analyzer in maintenance; measure p95 TAT impact and RC_DEVICE_MAINT blocks.
- **Initial state**: Deterministic from seed; 8–12 specimens; `timing_mode: simulated`, `policy_root` set so `failure_models.v0.1` and equipment load. Maintenance windows (e.g. DEV_CHEM_A_01 100–400 s) block START_RUN with RC_DEVICE_MAINT.
- **Episode length**: 200 steps.
- **Agents**: Scripted ops + scripted runners.
- **Reward config**: throughput_reward 1.0, violation_penalty 0.1.
- **SLA**: 3600 s.
- **Metrics**: p95_turnaround_s, blocked_by_reason_code (RC_DEVICE_MAINT).

### reagent_stockout — experimental

- **Goal**: Forced reagent shortage; low initial stock triggers RC_REAGENT_STOCKOUT, hold or reroute per reagent_policy; measure delays and violations.
- **Initial state**: Deterministic from seed; 5–8 specimens; `policy_root` set; `reagent_initial_stock`: R_CHEM_CORE capped so stockout occurs after a few runs.
- **Episode length**: 150 steps.
- **Agents**: Scripted ops + scripted runners.
- **Reward config**: throughput_reward 0.8, violation_penalty 0.15.
- **SLA**: 3600 s.
- **Metrics**: blocked_by_reason_code (RC_REAGENT_STOCKOUT), throughput, p95_turnaround_s.

## Metrics (per episode)

| Metric | Description |
|--------|-------------|
| `throughput` | Number of RELEASE_RESULT emits (released results). |
| `p50_turnaround_s` | 50th percentile accept→release time (s). |
| `p95_turnaround_s` | 95th percentile accept→release time (s). Meaningful when `timing_mode: simulated` (device service times drive completion). |
| `on_time_rate` | Fraction of specimens released within SLA (if SLA set). |
| `violations_by_invariant_id` | Count per invariant_id. |
| `blocked_by_reason_code` | Count per blocked_reason_code. |
| `critical_communication_compliance_rate` | ACK / NOTIFY ratio for critical results. **v0.2**: When escalation ladder is loaded, compliance requires a *compliant* ACK (attempt_id present, minimum_record_fields + tier required_fields, read_back_confirmed when required); release blocked until compliant ack. |
| `tokens_minted` | Count of MINT_TOKEN emits. |
| `tokens_consumed` | Count of token_consumed in step results. |
| `holds_count` | Count of HOLD_SPECIMEN emits. |
| `steps` | Number of env steps. |
| `detection_latency_s` | (adversarial_disruption) First violation timestamp − attack start timestamp (s). |
| `containment_success` | (adversarial_disruption) True if enforcement triggered before any release (or no release). |
| `attribution_confidence_proxy` | (adversarial_disruption) 1.0 when violations detected (audit log has agent_id + action chain). |
| `time_to_first_detected_security_violation` | (insider_key_misuse) First step (t_s) where BLOCKED with security reason (RBAC_ACTION_DENY, SIG_INVALID, SIG_KEY_REVOKED, SIG_KEY_EXPIRED, SIG_KEY_NOT_YET_VALID, etc.). |
| `fraction_of_attacks_contained` | (insider_key_misuse) Fraction of insider attack steps that resulted in BLOCKED with security reason. |
| `forensic_quality_score` | (insider_key_misuse) Proxy from step results: rbac_decision + signature_verification when applicable (0–1). |
| `sec.attack_success_rate` | (coord_risk) Fraction of episodes where the injection succeeded (e.g. spoof accepted, or measurable harm). |
| `sec.detection_latency_steps` | (coord_risk) Steps until first detection of injection (when applicable). |
| `sec.containment_time_steps` | (coord_risk) Steps until containment (when applicable). |
| `sec.stealth_success_rate` | (coord_risk) Fraction of episodes where the attack succeeded without detection (red-team metric). |
| `sec.time_to_attribution_steps` | (coord_risk) Steps until attacker attribution (red-team metric). |
| `sec.blast_radius_proxy` | (coord_risk) Proxy for scope of impact (red-team metric). |
| `robustness.regret_vs_nominal` | (coord_risk) p95 TAT delta vs nominal (no injection). |
| `robustness.resilience_score` | (coord_risk) Composite: 1 − normalized(Δp95) − α·violations_rate − β·blocks_rate (higher is better). |

## Output (results.json)

- `task`: Task id (e.g. throughput_sla).
- `num_episodes`, `base_seed`, `seeds`: Run config.
- `config`: max_steps, scripted_agents, reward_config.
- `policy_versions`: emits_vocab, catalogue_schema versions.
- `git_commit_hash`: Current commit (if available).
- `episodes`: List of `{ seed, metrics }` per episode.
- **metadata**: Always includes `run_duration_wall_s`, `run_duration_episodes_per_s`, `python_version`, `platform`. When `--llm-backend` is set also includes `llm_backend_id`, `llm_model_id`, `llm_error_rate`, `mean_llm_latency_ms`. See [Metrics contract](../contracts/metrics_contract.md#run-metadata-optional) and [Live LLM benchmark mode](../agents/llm_live.md).
- **coordination** (optional, coord_scale/coord_risk): `comm.msg_count`, `comm.p95_latency_ms`, `comm.drop_rate`; `coordination.timing` (stale_action_rate, mean_view_age_ms, p95_view_age_ms); `coordination.route` (replan_rate, mean_plan_time_ms, deadlock_avoids); `coordination.alloc` (gini_work_distribution, mean_bid, rebid_rate). Summary CSV and Pareto report include **resilience.component_perf**, **resilience.component_safety**, **resilience.component_security**, **resilience.component_coordination** when resilience scoring policy is used.

## Benchmark artifacts

| Artifact | Produced by | Contract |
|----------|-------------|----------|
| results.json | run-benchmark, eval-agent, generate-official-baselines | results.v0.2 (policy/schemas/results.v0.2.schema.json) |
| summary_v0.2.csv | summarize-results (streaming, bounded memory) | CI-stable; mean/std per metric |
| summary_v0.3.csv | summarize-results | Paper-grade; quantiles, 95% CI; containment_success_rate_ci_*; llm_confidence_ece_mean, llm_confidence_mce_mean (when applicable). |
| summary.csv | summarize-results | Same as summary_v0.2.csv |
| summary.md | summarize-results | Markdown table from v0.2 aggregates; when run_info exists, includes a **Run info** section (table) and a footer. |
| run_info.csv | summarize-results (when any result has metadata.run_duration_wall_s) | run_duration_wall_s, episodes_per_second per result |
| determinism_report.json, determinism_report.md | determinism-report | Hashes and v0.2 metrics comparison; markdown includes a **Checks** summary (e.g. 4/4 passed), run configuration table, result status, and hash comparison table. |
| pack_summary.csv, pack_gate.md | run-coordination-security-pack | Method x injection matrix; gate verdicts |

See [Metrics contract](../contracts/metrics_contract.md) for units and aggregation rules. For rate CIs, detector/LLM calibration, robust Pareto, and which uncertainty fields appear in each report, see [Uncertainty quantification](uncertainty_quantification.md) and [Uncertainty metrics in standard reports](../contracts/metrics_contract.md#uncertainty-metrics-in-standard-reports).

## CLI

```bash
# Quick sanity check (1 episode each of throughput_sla, adversarial_disruption, multi_site_stat; markdown + logs under labtrust_runs/)
labtrust quick-eval --seed 42

# Full benchmark run
labtrust run-benchmark --task throughput_sla --episodes 50 --seed 123 --out results.json
```

- **quick-eval**: 1 episode each of throughput_sla, adversarial_disruption, multi_site_stat; writes summary.md and logs under the output directory (default `labtrust_runs/`; runner creates a subdir such as `quick_eval_<timestamp>/`). Use `--seed` and `--out-dir` to customize.
- **run-benchmark** — `--task`: throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse, coord_scale, coord_risk. For coord_scale/coord_risk use `--coord-method <method_id>`; for coord_risk add `--injection <injection_id>`.
- `--episodes`: Number of episodes (default 10).
- `--seed`: Base seed (default 123).
- `--out`: Output JSON path (default results.json).
- `--log`: Optional JSONL path for episode step log.
- `--llm-backend`: Optional `deterministic`, `openai_live`, `anthropic_live`, or `ollama_live` to run with LLM agent or coordination (default: scripted agents). For coord_scale/coord_risk with LLM coordination methods, `ollama_live` uses local Ollama for proposals/bids. See [Live LLM benchmark mode](../agents/llm_live.md) and [LLM Coordination Protocol](llm_coordination_protocol.md).

## Timing mode

**timing_mode** is a first-class benchmark dimension. Use `--timing explicit|simulated` with `run-benchmark`, `quick-eval`, and `run-study` (CLI overrides task/spec default).

- **explicit** (default): Event `t_s` drives time; no simulated device service times. Golden suite and most benchmarks use this. **p95 TAT** is derived from step timestamps only (labeled in metrics as "Derived from step timestamps only (explicit mode)").
- **simulated**: Device capacity and cycle-time models apply; `START_RUN` schedules completion by service time (from `policy/equipment/equipment_registry.v0.1.yaml`). Device must be IDLE to start a run (`RC_DEVICE_BUSY` when RUNNING). **p95 TAT** is meaningful (accept→release includes queuing and device service time; labeled "Meaningful in simulated mode (device completion times)"). In simulated mode, episode metrics also include:
  - **device_utilization**: per-device busy_time / episode_time
  - **device_queue_length_mean**, **device_queue_length_max**: queue length statistics per device

### Which metrics are meaningful in which mode

| Metric | explicit | simulated |
|--------|----------|-----------|
| throughput, violations, blocked, tokens, holds | ✓ | ✓ |
| p50/p95 turnaround | Step timestamps only | Real completion times |
| on_time_rate | Step-based TAT | Real TAT vs SLA |
| device_utilization, device_queue_length_* | Not set (or 0) | Set |

## Determinism

Episodes are deterministic for a given seed: same task and base_seed produce identical episode metrics across runs. The smoke test runs 2 episodes twice with the same seed and asserts identical metrics.

## Long runs and profiling

For Layer 3 or many-episode runs, benchmark harness memory and CPU are not recorded by default. To profile: run with Python's `tracemalloc` (e.g. `python -c "import tracemalloc; tracemalloc.start(); ..."`) or use an external profiler (e.g. py-spy, memory_profiler). Run duration and episodes-per-second are written to `metadata.run_duration_wall_s` and `metadata.run_duration_episodes_per_s` in results.json and to `run_info.csv` when using `summarize-results`.

## Golden suite (transport and export)

The golden suite (`policy/golden/golden_scenarios.v0.1.yaml`) includes scenarios that explicitly exercise **transport** and **export** invariants:

- **GS-TRANSPORT-001**: Dispatch → tick → chain-of-custody sign → receive; verifies no violations and receipt-worthy emits (DISPATCH_TRANSPORT, TRANSPORT_TICK, CHAIN_OF_CUSTODY_SIGN, RECEIVE_TRANSPORT).
- **GS-TRANSPORT-002**: Temp excursion (via fault injection) triggers BLOCKED with `TRANSPORT_TEMP_EXCURSION` and violation **INV-TRANSPORT-001**.
- **GS-COC-003**: Invalid/missing chain-of-custody (e.g. receive with unknown consignment) triggers BLOCKED with `TRANSPORT_CHAIN_OF_CUSTODY_BROKEN` and violation **INV-COC-001**.
- **GS-EXPORT-001**: After a normal episode, runs post-run hooks: `EXPORT_RECEIPTS`, `VERIFY_BUNDLE`, `EXPORT_FHIR`, then asserts output files exist and manifest validates against `evidence_bundle_manifest.v0.1.schema.json`. Export outputs are deterministic for a fixed seed; Receipt.v0.1 and EvidenceBundle manifest v0.1 are validated during the golden run.

Run the golden suite with `LABTRUST_RUN_GOLDEN=1` (see [CI](../operations/ci.md)).

## Security attack suite

A separate **security attack suite** provides a coverage harness for risks (jailbreaks/prompt injection, tool vulnerability, identity spoofing/replay, memory poisoning, observability). It is defined in `policy/golden/security_attack_suite.v0.1.yaml` and executed by `src/labtrust_gym/benchmarks/security_runner.py`. Each attack maps to a risk_id, control_id, and either a prompt-injection scenario (`scenario_ref`) or a pytest module (`test_ref`); expected outcome is **blocked** or **detected**. The suite is deterministic (fixed seed) and CI-runnable in smoke mode (only attacks with `smoke: true`).

- **CLI**: `labtrust run-security-suite --out <dir> [--seed 42] [--full]` writes `SECURITY/attack_results.json` and the full securitization packet (coverage.json, coverage.md, reason_codes.md, deps_inventory.json) under `<dir>/SECURITY/`.
- **Package-release**: The paper_v0.1 profile runs the security suite (smoke-only) and emits the SECURITY/ folder automatically.

See [Security attack suite and securitization packet](../risk-and-security/security_attack_suite.md) for artifact layout, coverage mapping, and verification (policy fingerprints).

## Official benchmark pack

A single-command benchmark pack for external researchers is available: **Official Benchmark Pack** (v0.1 default, v0.2 when running with live LLM). It runs a fixed set of tasks (core + coordination), scales, baselines, coordination methods, and the security suite; outputs baselines, SECURITY/, SAFETY_CASE/, and transparency log under one directory. With `--pipeline-mode llm_live`, the pack uses v0.2 policy and also writes `TRANSPARENCY_LOG/llm_live.json` (prompt hashes, tool registry fingerprint, model identifiers, latency/cost; no sensitive prompt text) and `live_evaluation_metadata.json` (model_id, temperature, tool_registry_fingerprint, allow_network). Use `--llm-backend openai_live|anthropic_live|ollama_live` to choose the live backend. For cross-provider comparison, use **`labtrust run-cross-provider-pack --out <dir> --providers openai_live,anthropic_live,ollama_live`** to run the pack once per backend and get per-provider dirs plus `summary_cross_provider.json`/`.md`. See [Official benchmark pack](official_benchmark_pack.md) for policy (v0.1 and v0.2), CLI (`labtrust run-official-pack --out <dir> [--pipeline-mode llm_live] [--llm-backend <backend>] [--allow-network]`), and expected output tree.
