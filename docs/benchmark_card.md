# LabTrust-Gym Benchmark Card

## Scope

Blood Sciences lane: specimen reception, accessioning, pre-analytics, routine and STAT analytics, QC, critical result notification, and release. Multi-site transport (hub + acute) with consignments and chain-of-custody.

## Invariants and enforcement

- **Invariant registry** (v1.0): zone movement (INV-ZONE-001), co-location (INV-ZONE-002), restricted door (INV-ZONE-004, INV-ZONE-005), critical ack (INV-CRIT-002, INV-CRIT-004–006), stability (INV-STAB-BIOCHEM-*), transport (INV-COC-001, INV-TRANSPORT-001), tokens (INV-TOK-*), etc.
- **Enforcement**: optional throttle, kill_switch, freeze_zone, forensic_freeze via `policy/enforcement/enforcement_map.v0.1.yaml`.

## Tasks (A–F)

| Task | Description | SLA |
|------|-------------|-----|
| TaskA | Throughput under SLA | 3600 s |
| TaskB | STAT insertion under load | 1800 s |
| TaskC | QC fail cascade | — |
| TaskD | Adversarial disruption | 3600 s |
| TaskE | Multi-site STAT (transport latency) | 2400 s |
| TaskF | Insider + key misuse (RBAC, forged sig, replay, token misuse) | 3600 s |

## Baselines

- **scripted_ops_v1** (ops + runner): deterministic policy; used in reproduce and package-release.
- **adversary_v1** (TaskD): scripted adversary agent.
- **insider_v1** (TaskF): deterministic insider adversary (phases 1–5: forbidden action, forged sig, replay, **revoked key** → SIG_KEY_REVOKED, token misuse); TaskF runs with **strict_signatures: True**; study sweep **strict_signatures** on/off shows effect on containment.
- **ppo_v1**, **llm_safe_v1**: optional; see MARL/LLM baselines.

## Timing mode (first-class dimension)

Use `--timing explicit|simulated` with `run-benchmark`, `quick-eval`, and `run-study`. Task definitions can specify `timing_mode`; CLI overrides it.

- **explicit**: Step timestamps only; p95 TAT is derived from step times. No device utilization or queue stats. Golden scenarios use explicit.
- **simulated**: Device completion times; p95 TAT is meaningful. Metrics include `device_utilization` (busy_time / episode_time per device), `device_queue_length_mean`, `device_queue_length_max`. See [Benchmarks](benchmarks.md#timing-mode) for which metrics are meaningful in which mode.

## Results schema (v0.2) and leaderboard

Benchmark outputs conform to **results.v0.2** (`policy/schemas/results.v0.2.schema.json`): `task`, `seeds`, `policy_fingerprint`, `partner_id`, `git_sha`, `agent_baseline_id`, `episodes` with metrics (throughput, p50/p95 TAT, timing_mode, p95_turnaround_s_note, on_time_rate, violations, critical_communication_compliance_rate, detection_latency_s, containment_success; in simulated mode also device_utilization, device_queue_length_mean, device_queue_length_max).

- **Summarize**: `labtrust summarize-results --in <dir_or_files> --out <dir>` writes a wide **summary.csv** and **summary.md** (mean/std grouped by task + baseline + partner_id).
- **Official baseline table**: Frozen results and summary table are in `benchmarks/baselines_official/v0.1/` (and v0.2). See **How official baselines are generated** below.

### How official baselines are generated

Official baseline results are **regenerated and frozen** with:

```bash
labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 200 --seed 123
```

- **CLI**: `--out <dir>` (required), `--episodes <int>` (default 200), `--seed <int>` (default 123), `--timing explicit|simulated` (default explicit), `--partner <partner_id>` (optional), `--force` (allow overwrite).
- **Registry**: Task → baseline mapping is read from `benchmarks/baseline_registry.v0.1.yaml` (official_tasks: task, baseline_id). Not hard-coded in the CLI.
- **Tasks**: Runs Tasks A–F with the official baselines: TaskA/B/C/E → scripted_ops_v1, TaskD → adversary_v1, TaskF → insider_v1.
- **Output layout** (stable directory structure and filenames):
  - `results/TaskA_scripted_ops.json`, `results/TaskB_scripted_ops.json`, `results/TaskC_scripted_ops.json`, `results/TaskD_adversary.json`, `results/TaskE_scripted_ops.json`, `results/TaskF_insider.json` (each validated against `policy/schemas/results.v0.2.schema.json` after write).
  - `summary.csv` and `summary.md` (via the existing summarize-results pipeline).
  - `metadata.json`: git_sha, policy_fingerprint, cli_args (out, episodes, seed, timing, partner, force), tasks, baseline_ids / agent_baseline_ids, timestamp (deterministic when seed is provided).
- **Overwrite**: The command **refuses to overwrite** an existing output directory unless `--force` is passed.
- **Determinism**: For fixed `--seed` and `--episodes` (and `--timing explicit`), a contributor can regenerate baselines locally and get the same episode metrics. Timestamp in metadata is deterministic when seed is set.
- **CI**: The command is intended for manual or nightly runs (e.g. release prep); it is not part of the default CI pipeline. Tests use small episodes (e.g. 2) and fixed seed and run offline without network or GPU.

### v0.2 directory meaning and regeneration procedure

- **v0.2** is the current official baseline version. The directory `benchmarks/baselines_official/v0.2/` contains:
  - `results/`: one JSON file per task (schema v0.2).
  - `summary.csv`, `summary.md`: aggregated metrics (mean/std by task + baseline).
  - `metadata.json`: version, git_sha, policy_fingerprint, cli_args (out, episodes, seed, timing, partner, force), tasks, baseline_ids, agent_baseline_ids, timestamp.
- **Regeneration procedure**: From repo root, run `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 200 --seed 123`. Optional: `--timing simulated`, `--partner hsl_like`. To overwrite an existing v0.2 dir, add `--force`. Compare your run by passing both the official results dir and your results to `labtrust summarize-results --in benchmarks/baselines_official/v0.2/results <your_results> --out <out_dir>`.

## Known limitations and non-goals

- Golden suite: some scenarios (e.g. zone door alarm) may depend on enforcement or timing. The suite **includes transport and export**: GS-TRANSPORT-001/002 (dispatch, tick, chain-of-custody, receive; temp excursion), GS-COC-003 (chain-of-custody broken), GS-EXPORT-001 (post-run hooks: export receipts, verify bundle, export FHIR; output files and manifest validated).
- Full FHIR validation: export is minimal structural; no terminology server.
- Transport: scripted agents do not yet emit DISPATCH_TRANSPORT; TaskE runs without transport actions unless extended.
