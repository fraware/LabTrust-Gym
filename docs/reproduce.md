# Reproducing results and figures

A single CLI path reproduces a minimal set of study results and figures: a small ablation sweep (trust on/off, dual approval on/off) for **TaskA** and **TaskC**, then plots and data tables.

## Requirements

- `pip install -e ".[env,plots]"` (PettingZoo + matplotlib for study runner and plots)
- Run from repo root (or a directory that has `policy/` as ancestor)

## Commands

### Minimal run (few episodes, fast)

```bash
labtrust reproduce --profile minimal
```

- **Sweep**: `trust_skeleton` [on, off] × `dual_approval` [on, off] → 4 conditions per task.
- **Tasks**: TaskA, TaskC (2 study runs).
- **Episodes per condition**: 2 (or 1 when `LABTRUST_REPRO_SMOKE=1`).
- **Output**: `runs/repro_minimal_<YYYYMMDD_HHMMSS>/` with:
  - `spec_TaskA.yaml`, `spec_TaskC.yaml`
  - `taska/` and `taskc/`: `manifest.json`, `conditions.jsonl`, `results/`, `logs/`, `figures/`, `figures/data_tables/`

### Full run (more episodes)

```bash
labtrust reproduce --profile full
```

- Same sweep and tasks; **4 episodes** per condition (or 1 when `LABTRUST_REPRO_SMOKE=1`).
- Output: `runs/repro_full_<YYYYMMDD_HHMMSS>/` with the same layout.

### Custom output directory

```bash
labtrust reproduce --profile minimal --out runs/my_repro
```

Writes under `runs/my_repro/` (relative to repo root if not absolute).

## Expected runtime

- **Minimal** (2 episodes/condition, 4 conditions × 2 tasks = 8 study runs): about **1–3 minutes** on a typical laptop, depending on hardware.
- **Minimal with smoke** (`LABTRUST_REPRO_SMOKE=1`, 1 episode/condition): about **30–90 seconds**.
- **Full** (4 episodes/condition): about **2–6 minutes**.

Exact times depend on CPU and whether timing is `explicit` (faster) or `simulated`.

## Smoke test (CI / validation)

To only check that the command runs in minimal mode with a tiny episode count:

```bash
LABTRUST_REPRO_SMOKE=1 labtrust reproduce --profile minimal --out runs/repro_smoke
```

With `LABTRUST_REPRO_SMOKE=1`, every condition runs **1 episode** regardless of profile. The test `tests/test_reproduce_smoke.py` runs this under pytest when the env var is set.

## Output layout

```
runs/repro_minimal_<timestamp>/
  spec_TaskA.yaml
  spec_TaskC.yaml
  taska/
    manifest.json
    conditions.jsonl
    results/cond_0/results.json ... cond_3/results.json
    logs/cond_0/episodes.jsonl ...
    figures/
      throughput_vs_violations.png, .svg
      trust_cost_vs_p95_tat.png, .svg
      violations_by_invariant_id.png, .svg
      blocked_by_reason_code_top10.png, .svg
      critical_compliance_by_condition.png, .svg
    figures/data_tables/
      throughput_vs_violations.csv
      trust_cost_vs_p95_tat.csv
      violations_by_invariant_id.csv
      blocked_by_reason_code_top10.csv
      critical_compliance_by_condition.csv
  taskc/
    (same structure)
```

## See also

- [Studies and plots](studies.md) for the full study runner and plotting pipeline
- [Benchmarks](benchmarks.md) for task definitions and metrics
