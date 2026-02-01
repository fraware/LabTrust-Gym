# Study runner

The study runner executes benchmark tasks with **controlled ablations** and writes a **reproducible artifact directory**. Same spec, same code, and same seeds produce identical manifest and per-condition result hashes.

## StudySpec (YAML)

A study spec defines:

| Field | Required | Description |
|-------|----------|-------------|
| `task` | Yes | `TaskA`, `TaskB`, `TaskC`, `TaskD`, `TaskE`, or `TaskF` (or full task name). |
| `episodes` | Yes | Number of episodes per condition. |
| `seed_base` | Yes | Base seed; condition seed = `seed_base + condition_index`. |
| `timing_mode` | No | `explicit` (default) or `simulated`. |
| `ablations` | No | Object of ablation axes; each value is a list of options. Cartesian product defines conditions. |
| `agent_config` | No | `scripted_runner` (default), `scripted_ops`, `random`, or `placeholder`. |

### Ablations

Ablation axes are expanded as a **Cartesian product**. Each combination is one **condition**.

Supported axes (for schema and metadata; engine support may follow):

- **trust_skeleton**: `[on, off]`
- **rbac**: `[coarse, fine]`
- **dual_approval**: `[on, off]`
- **log_granularity**: `[minimal, full]`

Example: `trust_skeleton: [on, off]` and `rbac: [coarse]` → 2 conditions. Values are passed into `initial_state` overrides (e.g. `ablation_trust_skeleton`, `ablation_rbac`) so the engine can use them when implemented.

### Example spec

See `policy/studies/study_spec.example.v0.1.yaml`:

```yaml
task: TaskA
episodes: 4
seed_base: 42
timing_mode: explicit
ablations:
  trust_skeleton: [on, off]
  rbac: [coarse]
  dual_approval: [on]
  log_granularity: [minimal]
agent_config: scripted_runner
```

## Output structure

```
out_dir/
  manifest.json      # Commit hash (if git), policy versions, python version, deps snapshot; condition_ids; result_hashes
  conditions.jsonl   # One JSON line per condition (condition_id, condition, seeds, overrides)
  results/
    <condition_id>/
      results.json   # Same format as labtrust run-benchmark output
  logs/
    <condition_id>/
      episodes.jsonl # Episode step log (JSONL)
```

- **manifest.json**: Reproducibility metadata (git commit if available, policy versions, python version, optional deps snapshot); `condition_ids`; `result_hashes` (one SHA-256 per condition, over canonical JSON of results).
- **conditions.jsonl**: One line per condition; each line is a JSON object with `condition_id`, `condition` (ablation values), `task`, `episodes`, `seed_base`, `condition_seed`, `initial_state_overrides`, `agent_config`.
- **results/<condition_id>/results.json**: Full benchmark output for that condition (task, seeds, episodes, metrics, policy_versions, git_commit_hash).
- **logs/<condition_id>/episodes.jsonl**: Episode step log for that condition (same as `--log` in run-benchmark).

## CLI

```bash
labtrust run-study --spec policy/studies/study_spec.example.v0.1.yaml --out runs/20250101_120000
```

- `--spec`: Path to study spec YAML (relative to repo root or absolute).
- `--out`: Output directory; created if missing. Use a timestamp or name (e.g. `runs/my_ablation_study`).

Requires `.[env]` (PettingZoo/Gymnasium) for the benchmark runner.

## Determinism

- **Condition order**: Deterministic (sorted ablation keys; Cartesian product in fixed order).
- **Condition ID**: `cond_0`, `cond_1`, … (index in expansion).
- **Condition seed**: `seed_base + condition_index` (same spec ⇒ same seeds).
- **Result hashes**: SHA-256 of canonical JSON (sorted keys) of each condition’s `results.json`. Same spec + same code + same seeds ⇒ identical `result_hashes` in manifest across runs.

## Reproduce (minimal results + figures)

A single CLI path reproduces a minimal set of results and figures: a small ablation sweep (trust on/off, dual approval on/off) for **TaskA** and **TaskC**, then plots and data tables. See **[Reproduce](reproduce.md)** for exact commands and expected runtime.

```bash
labtrust reproduce --profile minimal   # few episodes
labtrust reproduce --profile full     # more episodes
```

Output: `runs/repro_<profile>_<timestamp>/taska/` and `taskc/` (each with manifest, results, logs, figures, data_tables). With `LABTRUST_REPRO_SMOKE=1`, episodes are set to 1 per condition for fast smoke testing.

## Schema

Study specs can be validated against `policy/studies/study_spec.schema.v0.1.json` (JSON Schema). The schema defines `task` (enum), `episodes` (integer ≥ 1), `seed_base` (integer), `timing_mode`, `ablations`, and `agent_config`.

## Generate plots

A **deterministic plotting pipeline** converts a study run into data tables (CSV) and paper-ready figures (PNG + SVG). Same study output ⇒ identical CSV tables (byte-for-byte); figures are generated from those tables.

### CLI

```bash
labtrust make-plots --run runs/<id>
```

- `--run`: Path to a study output directory (must contain `manifest.json` and `results/<condition_id>/results.json`).

Requires matplotlib: `pip install -e ".[plots]"` (or `.[env,plots]`).

### Output layout

After `make-plots`:

```
out_dir/figures/
  data_tables/           # Deterministic CSVs (same inputs => identical files)
    throughput_vs_violations.csv
    trust_cost_vs_p95_tat.csv
    violations_by_invariant_id.csv
    blocked_by_reason_code_top10.csv
    critical_compliance_by_condition.csv
  throughput_vs_violations.png, .svg
  trust_cost_vs_p95_tat.png, .svg
  violations_by_invariant_id.png, .svg
  blocked_by_reason_code_top10.png, .svg
  critical_compliance_by_condition.png, .svg
```

### Figures

| Figure | Description |
|--------|-------------|
| **throughput vs violations** | Scatter: x = violations (total per condition), y = mean throughput. One point per condition. |
| **trust cost vs p95 TAT** | Scatter: x = mean p95 turnaround (s), y = mean trust cost (tokens consumed + minted). One point per condition. |
| **violations by invariant_id** | Bar: invariant_id vs total count (aggregated across all conditions/episodes). |
| **blocked by reason_code (top 10)** | Bar: top 10 reason codes by blocked count (aggregated). |
| **critical compliance by condition** | Bar: condition_id vs mean critical_communication_compliance_rate. |

### Determinism

- **Data tables**: Computed from `results/<condition_id>/results.json` in a fixed order (condition_ids from manifest). Same run dir ⇒ identical CSV files. Tests in `tests/test_plots_tables_determinism.py` run `make_plots` twice and assert CSV contents match.
- **Plots**: PNG/SVG are generated from the same tables; byte-identical plots are not guaranteed (matplotlib backend/version), but the underlying data is.
