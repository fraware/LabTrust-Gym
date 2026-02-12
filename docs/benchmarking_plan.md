# Coordination Benchmarking Plan (Three Layers)

This document defines a three-layer benchmarking matrix so you can validate plumbing quickly (Layer 1), then run full coverage (Layer 2), then scale and timing (Layer 3) without wasting time on broken pipelines.

## Scale and timing

- **Scale config IDs** (from `policy/coordination/scale_configs.v0.1.yaml`):
  - **S**: `small_smoke` (fast smoke; 4 agents, 50 steps)
  - **M**: `medium_stress_signed_bus` (75 agents, 300 steps, timing_mode simulated)
  - **L**: `corridor_heavy` (200 agents, 150 steps) — designated **at-scale** profile; tested in coordination-nightly (1 episode). See [Scale and operational limits](scale_operational_limits.md).

- **Timing**: Use `--timing simulated` for Layer 3 to get realistic latency/TAT metrics; Layer 1/2 can use defaults (explicit or per-scale).

---

## Layer 1 — Sanity (fast)

**Goal**: Confirm all methods and tasks run without errors before investing in full matrix or scale.

- **coord_scale**: S scale (`small_smoke`), 3 seeds.
- **coord_risk**: S scale, 1 injection (e.g. `INJ-COMMS-POISON-001`), 3 seeds.
- **Methods**: New SOTA methods plus two baselines: `market_auction`, `kernel_whca`. Default list: `kernel_whca`, `market_auction`, `ripple_effect`, `group_evolving_experience_sharing`.

**Commands (per method `<id>`)**:

```bash
labtrust run-benchmark --task coord_scale --coord-method <id> --scale small_smoke --episodes 3 --seed 100 --out labtrust_runs/sota_sanity/<id>_coord_scale.json
labtrust run-benchmark --task coord_risk  --coord-method <id> --injection INJ-COMMS-POISON-001 --scale small_smoke --episodes 3 --seed 200 --out labtrust_runs/sota_sanity/<id>_coord_risk_poison.json
```

**Script**: `scripts/run_benchmarking_layer1_sanity.sh` (and `.ps1` for Windows) runs these for the default method list and writes under `labtrust_runs/sota_sanity/`.

**Full registry mode**: Set `LABTRUST_SANITY_FULL=1` to run coord_scale and coord_risk (with one injection plus coord_risk baseline `none`) for **every** `method_id` from `policy/coordination/coordination_methods.v0.1.yaml` (excluding `marl_ppo`). LLM methods run with `--llm-backend deterministic`. Use this to assert all individual methods work before running the security pack or full study.

```bash
LABTRUST_SANITY_FULL=1 ./scripts/run_benchmarking_layer1_sanity.sh
```

---

## Published baseline and comparing your run

**Canonical baseline (in repo):** `benchmarks/baselines_official/v0.2/` is the frozen official baseline for core tasks (throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse). It contains `results/*.json` (schema v0.2), `summary.csv`, `summary.md`, and `metadata.json`. Regenerate with the same episodes and seed for reproducibility:

```bash
labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force
```

**Comparing your run to the baseline:**

1. **Exact regression (CI):** Run `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v`. This runs the same tasks (episodes=3, seed=123, timing=explicit) and compares metrics to the committed v0.2 results; fails on any difference.
2. **Summary diff:** Generate a local baseline with the same args, then compare summary CSVs: `python scripts/compare_baseline_summary.py benchmarks/baselines_official/v0.2/summary.csv /path/to/your/summary.csv`. The script reports matching rows or differences in key columns.

**Publishing the baseline:** Run `./scripts/publish_baseline_artifact.sh` (or `.\scripts\publish_baseline_artifact.ps1` on Windows) to create a zip of `benchmarks/baselines_official/v0.2/`. Upload the zip to Zenodo or similar; record the DOI in this doc or in the repo README. The zip contains README.md with the regenerate command and repo citation.

---

## Layer 2 — Coverage (medium)

**Goal**: Full required method x risk matrix from the coordination study spec.

**Command**:

```bash
labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out labtrust_runs/sota_matrix

For **LLM-only with live backends** (openai_live, ollama_live, anthropic_live), use the dedicated spec and pass `--llm-backend`; see [Coordination studies](coordination_studies.md#llm-only-with-live-backends).
```

**Script**: `scripts/run_benchmarking_layer2_coverage.sh` (and `.ps1`) runs this single command.

---

## Layer 3 — Scale (heavy)

**Goal**: coord_scale and coord_risk at S/M/L scale; coord_risk with top 3 injections; 10–30 episodes per condition; simulated timing for latency/TAT.

- **coord_scale**: Scales S, M, L (one run per scale per method).
- **coord_risk**: Scales S, M, L x top 3 injections (e.g. `INJ-COMMS-POISON-001`, `INJ-ID-SPOOF-001`, `INJ-COLLUSION-001`).
- **Episodes**: 10–30 per cell (tune by cost/time).
- **Timing**: `--timing simulated`.

**Scale IDs**: `small_smoke` (S), `medium_stress_signed_bus` (M), `corridor_heavy` (L).

**Example (single method, one scale, one injection)**:

```bash
labtrust run-benchmark --task coord_risk --coord-method ripple_effect --injection INJ-COMMS-POISON-001 --scale medium_stress_signed_bus --episodes 15 --seed 300 --timing simulated --out labtrust_runs/sota_scale/ripple_effect_coord_risk_M_poison.json
```

**Script**: `scripts/run_benchmarking_layer3_scale.sh` (and `.ps1`) iterates methods x scales x (coord_scale or coord_risk with top 3 injections), with configurable episodes and seeds.

---

## Output layout

| Layer | Output root | Contents |
|-------|-------------|----------|
| 1 | `labtrust_runs/sota_sanity/` | `<id>_taskg.json`, `<id>_taskh_poison.json` per method |
| 2 | `labtrust_runs/sota_matrix/` | Study output: cells, summary, coverage |
| 3 | `labtrust_runs/sota_scale/` | Per method/scale/injection results (e.g. `<id>_taskg_<S|M|L>.json`, `<id>_taskh_<S|M|L>_<injection>.json`) |

---

## Security stress matrix (coordination security pack)

**Goal**: Stress all security tests (injections) against all coordination methods in a single, policy-driven matrix. Outputs are captured and gated the same way as the fixed pack.

**Command**:

```bash
labtrust run-coordination-security-pack --out <dir> [--methods-from fixed|full|path] [--injections-from fixed|critical|policy|path] [--seed 42]
```

- **Methods**: `fixed` = default from `policy/coordination/coordination_security_pack.v0.1.yaml` (3 methods); `full` = every `method_id` from `coordination_methods.v0.1.yaml` except `marl_ppo`; or a path to a file (one method_id per line or YAML list).
- **Injections**: `fixed` = config default (none + 5 INJ-*); `critical` = short high-signal list (none + 3 INJ-*); `policy` = all injection_ids from `injections.v0.2.yaml` that exist in `INJECTION_REGISTRY` (implemented injectors), with `none` first; or a path to a file.
- **Output**: `pack_results/<cell_id>/results.json`, `pack_summary.csv`, `pack_gate.md`, and (when the pack is run) `SECURITY/coordination_risk_matrix.csv` and `SECURITY/coordination_risk_matrix.md`. Each row has method_id, scale_id, injection_id, application_phase (when set), perf.*, safety.*, sec.* (including sec.stealth_success_rate, sec.time_to_attribution_steps where available). The risk matrix gives a single view of method x injection x phase outcomes (sec.attack_success_rate, sec.detection_latency_steps, verdict) for benchmarking and risk comparison. Gate rules are in `policy/coordination/coordination_security_pack_gate.v0.1.yaml`. Verdicts: PASS (threshold met), FAIL (with evidence), SKIP (not_applicable, no_data, disabled_by_config), not_supported. Cells for injection_ids without a rule receive SKIP (not_applicable).

**Interpretation**: Open `pack_gate.md` for PASS/FAIL/SKIP/not_supported per cell. Use `labtrust summarize-coordination --in <dir> --out <dir>` to aggregate pack_summary (or study summary) into SOTA leaderboard and method-class comparison. For a single lab report bundle (summarize + recommend + LAB_COORDINATION_REPORT.md), use `labtrust build-lab-coordination-report --pack-dir <dir>`; see [Lab coordination report](lab_coordination_report.md). See also [Security attack suite](security_attack_suite.md#coordination-security-pack-internal-regression) and [Coordination studies](coordination_studies.md).

**Layering**: Layer 1 (sanity) confirms each method runs; the security pack (fixed matrix) runs in coordination-nightly CI; use `--methods-from full --injections-from policy` for a full method x injection run (e.g. weekly or manual).

**Paper release**: The paper-ready profile (`labtrust package-release --profile paper_v0.1`) can optionally include the coordination security pack and lab report: use `--include-coordination-pack`. The artifact then contains `_coordination_pack/` (pack_summary.csv, pack_gate.md, LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.*) and a coordination matrix built from the pack. See [Lab coordination report](lab_coordination_report.md) and [Paper-ready release](paper_ready.md).

---

## CLI reference (run-benchmark)

- `--task`: `coord_scale` or `coord_risk`.
- `--coord-method`: Method id (e.g. `kernel_whca`, `market_auction`, `ripple_effect`, `group_evolving_experience_sharing`).
- `--scale`: Scale config id (`small_smoke`, `medium_stress_signed_bus`, `corridor_heavy`). Optional; uses task default if omitted.
- `--timing`: `explicit` or `simulated`. Optional; uses task/scale default if omitted.
- `--injection`: For coord_risk only (e.g. `INJ-COMMS-POISON-001`).
- `--episodes`, `--seed`, `--out`: Episode count, base seed, output JSON path.

---

## Verification and test skips

**Running the plan**: Layer 1 and Layer 3 use shell scripts (`.sh`); on Windows use the `.ps1` equivalents or run the same `labtrust run-benchmark` commands in a loop. Ensure scripts use LF line endings (`.gitattributes` sets `*.sh text eol=lf`); if bash reports `$'\r': command not found`, convert the script to LF or use the PowerShell script. Layer 2 is a single command; the security pack is a single command (can be long for full matrix).

**Coordination pytest skips** (in `tests/test_coordination_methods_smoke.py`): Two tests are skipped by design:

1. **`test_coordination_method_smoke_50_steps[marl_ppo]`** — `marl_ppo` requires a trained model (not provided in smoke). Skipped so the smoke suite does not require Stable-Baselines3 or a checkpoint.
2. **`test_marl_ppo_skip_if_no_deps`** — This test runs only when the `marl` extra is **not** installed: it checks that `make_coordination_method("marl_ppo", ...)` raises when SB3 is missing. When SB3 **is** installed, the test is skipped so the suite does not depend on the "no deps" environment.

**LLM and API keys**: `llm_constrained` and other LLM coordination methods are exercised in the smoke using a **deterministic** in-process backend (no network, no API key). Your `.env` with `OPENAI_API_KEY` is used only when you run **live** benchmarks (e.g. `labtrust run-benchmark --coord-method llm_constrained --llm-backend openai_live`). The smoke and contract tests never call the API.

All other coordination methods (including `llm_constrained` with the deterministic agent) are exercised in the smoke and in the contract test (`test_coordination_method_contract`).

---

## Performance notes

- **Policy hot path:** Policy loading is cached where applicable (e.g. adversarial detection policy per path, policy RAG chunks once per process). No redundant load per step on the hot path.
- **Large episode logs:** For very long runs (many episodes or long horizons), episode log and JSONL export can be large; consider streaming or chunking if memory or disk becomes a concern. Summarize/export prefers single-pass or incremental where applicable.
