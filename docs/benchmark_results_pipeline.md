# Benchmark results pipeline

This document describes the path from a **coordination method sweep** (Prime Intellect live) to **presentation and analysis artifacts**.

## Artifacts in the run directory

Produced by `scripts/run_all_methods_prime_live_full.py`:

| File | Role |
|------|------|
| `run_meta.json` | Sweep parameters (scale, model, seed, episodes, start time). |
| `method_status.jsonl` | Append-only `method_start` / `method_end` events. |
| `all_methods_full_table.json` | Latest row per method (crash-safe progress). |
| `run_summary.json` | Written only when **all** methods in the sweep finish. |
| `{scale_id}_{method}_none/results.json` | Per-method benchmark cell. |

## Presentation bundle (default location)

By default, reports are written to a **sibling folder** `{run_directory_name}_report`:

- `index.html` — Briefing, KPIs, analysis highlights, Chart.js comparisons (SRI-pinned CDN, reduced-motion aware), **sortable** method matrix, filter, skip link, export links.
- `snapshot.json` — Full row-level data for automation / CI (`schema_version` included).
- `analysis_summary.json` — Cross-method aggregates, flags, insight strings (`schema_version` included).
- `methods_matrix.csv` — Same rows as the table for pandas / R / spreadsheets.
- `manifest.json` — Bundle index (artifact descriptions, headline analytics, optional `git_sha_from_cells`).

## Commands

**After a run (or with a copied run tree on another machine):**

```bash
python scripts/benchmark_suite.py publish --run-dir runs/gcp_full_benchmark
```

**Custom output folder:**

```bash
python scripts/benchmark_suite.py publish --run-dir runs/my_sweep --out-dir runs/my_report
```

**Show the default report path for a run:**

```bash
python scripts/benchmark_suite.py paths --run-dir runs/gcp_full_benchmark
```

**Open the HTML in a browser:**

```bash
python scripts/benchmark_suite.py open --report-dir runs/gcp_full_benchmark_report
```

Equivalent lower-level entry (same output):

```bash
python scripts/build_benchmark_report.py --run-dir runs/gcp_full_benchmark
```

## Optional: publish when the orchestrator exits

At the end of a sweep (complete or with failures), generate the bundle automatically:

```bash
python scripts/run_all_methods_prime_live_full.py --out-dir runs/my_sweep --publish-report
```

If the process is killed before Python reaches the end of `main()`, run `benchmark_suite.py publish` manually on the partial folder.

## Interpreting PASS vs outcomes

Strict **PASS** in the orchestrator checks **live harness** requirements (backend, calls, error rate, tokens/latency evidence for LLM methods). It does **not** require non-zero throughput or transport. Use the **Analysis highlights** section and outcome charts for task-level comparison.

## Python API

Analytics and paths (stable import from the package):

```python
from labtrust_gym.benchmarks.presentation.pipeline import (
    compute_run_analytics,
    default_report_out_dir,
    load_run_meta,
    load_run_summary,
)
```

Full HTML generation lives in `scripts/build_benchmark_report.py` as `generate_benchmark_report()`; tests load that module with `importlib` (see `tests/test_build_benchmark_report.py`).
