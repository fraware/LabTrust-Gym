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

## Metrics (per episode)

| Metric | Description |
|--------|-------------|
| `throughput` | Number of RELEASE_RESULT emits (released results). |
| `p50_turnaround_s` | 50th percentile accept→release time (s). |
| `p95_turnaround_s` | 95th percentile accept→release time (s). Meaningful when `timing_mode: simulated` (device service times drive completion). |
| `on_time_rate` | Fraction of specimens released within SLA (if SLA set). |
| `violations_by_invariant_id` | Count per invariant_id. |
| `blocked_by_reason_code` | Count per blocked_reason_code. |
| `critical_communication_compliance_rate` | ACK / NOTIFY ratio for critical results. |
| `tokens_minted` | Count of MINT_TOKEN emits. |
| `tokens_consumed` | Count of token_consumed in step results. |
| `holds_count` | Count of HOLD_SPECIMEN emits. |
| `steps` | Number of env steps. |

## Output (results.json)

- `task`: Task name (e.g. TaskA).
- `num_episodes`, `base_seed`, `seeds`: Run config.
- `config`: max_steps, scripted_agents, reward_config.
- `policy_versions`: emits_vocab, catalogue_schema versions.
- `git_commit_hash`: Current commit (if available).
- `episodes`: List of `{ seed, metrics }` per episode.

## CLI

```bash
labtrust run-benchmark --task TaskA --episodes 50 --seed 123 --out results.json
```

- `--task`: TaskA, TaskB, TaskC (or full name).
- `--episodes`: Number of episodes (default 10).
- `--seed`: Base seed (default 123).
- `--out`: Output JSON path (default results.json).

## Timing mode

- **explicit** (default): Event `t_s` drives time; no simulated device service times. Golden suite and most benchmarks use this. p95 TAT is derived from step timestamps only.
- **simulated**: Device capacity and cycle-time models apply; `START_RUN` schedules completion by service time (from `policy/equipment/equipment_registry.v0.1.yaml`). Device must be IDLE to start a run (`RC_DEVICE_BUSY` when RUNNING). p95 TAT becomes meaningful (accept→release includes queuing and device service time).

Set `initial_state.timing_mode: "simulated"` in task config to enable simulated timing for benchmarks.

## Determinism

Episodes are deterministic for a given seed: same task and base_seed produce identical episode metrics across runs. The smoke test runs 2 episodes twice with the same seed and asserts identical metrics.
