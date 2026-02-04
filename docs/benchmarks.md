# LabTrust-Gym Benchmarks

Benchmark harness for running multiple episodes with fixed seeds, recording metrics, and outputting JSON.

## Tasks

### TaskA_ThroughputSLA (TaskA)

- **Goal**: Throughput under SLA; routine load.
- **Initial state**: Deterministic from seed; 3–5 specimens at reception.
- **Episode length**: 80 steps.
- **Agents**: Scripted ops + scripted runners (ops_0, runner_0, runner_1).
- **Reward config**: `throughput_reward: 1.0`.
- **SLA**: 3600 s turnaround (accept→release) for on-time rate.

### TaskB_STATInsertionUnderLoad (TaskB)

- **Goal**: STAT specimens inserted under routine load; prioritization.
- **Initial state**: Deterministic from seed; 4–5 specimens.
- **Episode length**: 120 steps.
- **Agents**: Scripted ops + scripted runners.
- **Reward config**: `throughput_reward: 1.0`, `violation_penalty: 0.1`.
- **SLA**: 1800 s for on-time rate.

### TaskC_QCFailCascade (TaskC)

- **Goal**: QC fail on one device; routing and cascade behavior.
- **Initial state**: Deterministic from seed; 2–3 specimens.
- **Episode length**: 100 steps.
- **Agents**: Scripted ops + scripted runners.
- **Reward config**: None (reward=0 initially).
- **SLA**: None.

### TaskD_AdversarialDisruption (TaskD)

- **Goal**: Detection, containment, and attribution under adversarial disruption.
- **Initial state**: Deterministic from seed; 3–4 specimens.
- **Episode length**: 80 steps.
- **Agents**: Scripted ops + scripted runners + **adversary_0** (deterministic adversarial policy).
- **Adversary behaviors**: Misroute racks (QUEUE_RUN to wrong device), attempt unauthorized restricted door, attempt expired token/replay, leave door open (no TICK mitigation).
- **Reward config**: throughput_reward 0.5, violation_penalty 0.2, blocked_penalty 0.1.
- **SLA**: 3600 s.
- **Metrics**: `detection_latency_s` (first violation ts − attack start), `containment_success` (enforcement before unsafe release), `attribution_confidence_proxy` (audit has agent_id + action chain).

### TaskE_MultiSiteSTAT (TaskE)

- **Goal**: Multi-site STAT: acute node STAT specimens, hub routine queue; transport latency; SLA + violations + critical comm compliance.
- **Initial state**: Deterministic from seed; 3–4 specimens.
- **Episode length**: 150 steps.
- **Agents**: Scripted ops + scripted runners (ops_0, runner_0, runner_1).
- **Reward config**: `throughput_reward: 1.0`, `violation_penalty: 0.1`.
- **SLA**: 2400 s turnaround.

### TaskF_InsiderAndKeyMisuse (TaskF)

- **Goal**: Trust skeleton under insider + key misuse: RBAC deny, forged signature, replay, token misuse; measure containment and forensic quality.
- **Initial state**: Deterministic from seed; 2–3 specimens.
- **Episode length**: 50 steps.
- **Agents**: Scripted ops + runner_0 + **adversary_insider_0** (A_INSIDER_0 with limited RBAC).
- **Attack phases** (deterministic steps): (1) RELEASE_RESULT → RBAC_ACTION_DENY; (2) MOVE with forged signature → SIG_INVALID; (3) replay same signature → SIG_INVALID; (4) RELEASE_RESULT_OVERRIDE with fake token → RBAC_ACTION_DENY.
- **Reward config**: throughput_reward 0.3, violation_penalty 0.2, blocked_penalty 0.1.
- **Metrics**: `time_to_first_detected_security_violation`, `fraction_of_attacks_contained`, `forensic_quality_score` (receipts include signature + RBAC + token evidence).
- **Study sweep**: `policy/studies/study_spec.taskf_insider.v0.1.yaml` sweeps **strict_signatures** [false, true] to show effect on containment.

### TaskG_COORD_SCALE (TaskG)

- **Goal**: Coordination at scale under nominal conditions; compare coordination methods (centralized, hierarchical, market, gossip, swarm, optional LLM).
- **Initial state**: Generated deterministically by scale config (num_agents, num_devices, num_sites, specimens_per_min, horizon_steps); see [Coordination scale](coordination_scale.md).
- **Episode length**: From scale config `horizon_steps` (default 200).
- **Agents**: Scale-defined workers (A_WORKER_0001, …); coordination method proposes actions for all agents.
- **Reward config**: `throughput_reward`, `violation_penalty`.
- **CLI**: `labtrust run-benchmark --task TaskG_COORD_SCALE --coord-method <method_id> --episodes 1 --seed 42 --out results.json`.

### TaskH_COORD_RISK (TaskH)

- **Goal**: Coordination under injected risks; measure security and robustness (attack_success_rate, detection_latency, containment_time, resilience_score).
- **Initial state**: Same as TaskG (scale config).
- **Episode length**: Same as TaskG.
- **Agents**: Same as TaskG; risk injector can mutate obs, messages, or actions (deterministic, auditable).
- **Injections**: Configured in `policy/coordination/coordination_study_spec.v0.1.yaml` (e.g. INJ-COMMS-POISON-001, INJ-ID-SPOOF-001, INJ-COLLUSION-001). INJ-ID-SPOOF-001 must be blocked when strict signatures are enabled.
- **CLI**: `labtrust run-benchmark --task TaskH_COORD_RISK --coord-method <method_id> --injection <injection_id> --episodes 1 --seed 42 --out results.json`.
- **Study**: `labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out <dir>` produces per-cell results, summary_coord.csv, and pareto.md. See [Coordination studies](coordination_studies.md).

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
| `detection_latency_s` | (TaskD) First violation timestamp − attack start timestamp (s). |
| `containment_success` | (TaskD) True if enforcement triggered before any release (or no release). |
| `attribution_confidence_proxy` | (TaskD) 1.0 when violations detected (audit log has agent_id + action chain). |
| `time_to_first_detected_security_violation` | (TaskF) First step (t_s) where BLOCKED with security reason (RBAC_ACTION_DENY, SIG_INVALID, SIG_KEY_REVOKED, SIG_KEY_EXPIRED, SIG_KEY_NOT_YET_VALID, etc.). |
| `fraction_of_attacks_contained` | (TaskF) Fraction of insider attack steps that resulted in BLOCKED with security reason. |
| `forensic_quality_score` | (TaskF) Proxy from step results: rbac_decision + signature_verification when applicable (0–1). |
| `sec.attack_success_rate` | (TaskH) Fraction of episodes where the injection succeeded (e.g. spoof accepted, or measurable harm). |
| `sec.detection_latency_steps` | (TaskH) Steps until first detection of injection (when applicable). |
| `sec.containment_time_steps` | (TaskH) Steps until containment (when applicable). |
| `robustness.regret_vs_nominal` | (TaskH) p95 TAT delta vs nominal (no injection). |
| `robustness.resilience_score` | (TaskH) Composite: 1 − normalized(Δp95) − α·violations_rate − β·blocks_rate (higher is better). |

## Output (results.json)

- `task`: Task name (e.g. TaskA).
- `num_episodes`, `base_seed`, `seeds`: Run config.
- `config`: max_steps, scripted_agents, reward_config.
- `policy_versions`: emits_vocab, catalogue_schema versions.
- `git_commit_hash`: Current commit (if available).
- `episodes`: List of `{ seed, metrics }` per episode.
- **metadata** (optional, when `--llm-backend` is set): `llm_backend_id`, `llm_model_id`, `llm_error_rate`, `mean_llm_latency_ms`. See [Live LLM benchmark mode](llm_live.md).
- **coordination** (optional, TaskG/TaskH): `comm.msg_count`, `comm.p95_latency_ms`, `comm.drop_rate`; `coordination.timing` (stale_action_rate, mean_view_age_ms, p95_view_age_ms); `coordination.route` (replan_rate, mean_plan_time_ms, deadlock_avoids); `coordination.alloc` (gini_work_distribution, mean_bid, rebid_rate). Summary CSV and Pareto report include **resilience.component_perf**, **resilience.component_safety**, **resilience.component_security**, **resilience.component_coordination** when resilience scoring policy is used.

## CLI

```bash
# Quick sanity check (1 episode each of TaskA, TaskD, TaskE; markdown + logs under labtrust_runs/)
labtrust quick-eval --seed 42

# Full benchmark run
labtrust run-benchmark --task TaskA --episodes 50 --seed 123 --out results.json
```

- **quick-eval**: 1 episode each of TaskA, TaskD, TaskE; writes summary.md and logs under `./labtrust_runs/quick_eval_<timestamp>/` (`--seed`, `--out-dir`).
- **run-benchmark** — `--task`: TaskA, TaskB, TaskC, TaskD, TaskE, TaskF, TaskG_COORD_SCALE, TaskH_COORD_RISK (or short names). For TaskG/TaskH use `--coord-method <method_id>`; for TaskH add `--injection <injection_id>`.
- `--episodes`: Number of episodes (default 10).
- `--seed`: Base seed (default 123).
- `--out`: Output JSON path (default results.json).
- `--log`: Optional JSONL path for episode step log.
- `--llm-backend`: Optional `deterministic` or `openai_live` to run with LLM agent (default: scripted agents). See [Live LLM benchmark mode](llm_live.md).

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

## Golden suite (transport and export)

The golden suite (`policy/golden/golden_scenarios.v0.1.yaml`) includes scenarios that explicitly exercise **transport** and **export** invariants:

- **GS-TRANSPORT-001**: Dispatch → tick → chain-of-custody sign → receive; verifies no violations and receipt-worthy emits (DISPATCH_TRANSPORT, TRANSPORT_TICK, CHAIN_OF_CUSTODY_SIGN, RECEIVE_TRANSPORT).
- **GS-TRANSPORT-002**: Temp excursion (via fault injection) triggers BLOCKED with `TRANSPORT_TEMP_EXCURSION` and violation **INV-TRANSPORT-001**.
- **GS-COC-003**: Invalid/missing chain-of-custody (e.g. receive with unknown consignment) triggers BLOCKED with `TRANSPORT_CHAIN_OF_CUSTODY_BROKEN` and violation **INV-COC-001**.
- **GS-EXPORT-001**: After a normal episode, runs post-run hooks: `EXPORT_RECEIPTS`, `VERIFY_BUNDLE`, `EXPORT_FHIR`, then asserts output files exist and manifest validates against `evidence_bundle_manifest.v0.1.schema.json`. Export outputs are deterministic for a fixed seed; Receipt.v0.1 and EvidenceBundle manifest v0.1 are validated during the golden run.

Run the golden suite with `LABTRUST_RUN_GOLDEN=1` (see [CI](ci.md)).
