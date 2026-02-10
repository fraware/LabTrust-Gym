# Coordination Matrix

The Coordination at Scale x Resilience Matrix is built from llm_live coordination runs. Policy files define semantics; the builder produces a schema-valid JSON artifact.

**llm_live-only.** This feature does not run for offline or deterministic pipelines. The builder refuses non-llm_live run directories with an explicit error. No changes to offline pipeline defaults; new CLI and flags are opt-in.

---

## How to run

**Build matrix from an existing run directory:**

```bash
labtrust build-coordination-matrix --run <run_dir> --out <out_path_or_dir>
```

- If `--out` is a directory, the artifact is written as `coordination_matrix.v0.1.json` in that directory.
- Example: `labtrust build-coordination-matrix --run runs/coord_20250101 --out runs/coord_20250101`

**Emit matrix at the end of a coordination study (llm_live only):**

```bash
labtrust run-coordination-study --spec <spec.yaml> --out <out_dir> --llm-backend openai_live --emit-coordination-matrix
```

- Requires `--llm-backend openai_live` or `ollama_live`. If the pipeline is not llm_live, the CLI errors with an explicit message instead of silently skipping.
- The matrix is written into the study output directory as `coordination_matrix.v0.1.json`.

---

## Sources and column map

Source tables and column names are defined by **policy/coordination/coordination_matrix_column_map.v0.1.yaml**.

- **Clean metrics:** First available of `summary_coord.csv`, `summary_v0.2.csv`, `results.json` under the run directory (or subdirs). Rows keyed by `(scale_id, method_id)`.
- **Attacked metrics:** First available of `pack_summary.csv`, `security_attack_suite.json`, `summary_coord.csv`. Rows may include `injection_id`; see aggregation below.

The column map lists, per metric ID, `preferred_sources`, `candidates` (column names), `transform`, and `missing_policy`. The builder resolves metrics deterministically; it does not guess column names.

---

## Attack aggregation (worst-case, non-optional)

For each `(scale_id, method_id)` the builder may see multiple rows (one per injection). **Aggregation is worst-case and is the canonical rule** for standards of excellence; it is not optional and is not configurable.

- **lower_is_better** metrics (e.g. attack_success_rate): take the **max** across injections (worst outcome).
- **higher_is_better** metrics: take the **min** across injections (worst outcome).

Averaging across injections is not used, so a single catastrophic injection cannot be hidden. This rule is implemented in `src/labtrust_gym/studies/coordination_matrix_builder.py` (`_aggregate_attacked_worst_case`) and is fixed at build time. If the run has only one row per `(scale_id, method_id)`, that value is used as-is.

---

## Policy files (Phase 1)

- **coordination_matrix_inputs.v0.1.yaml** — Scope (llm_live only), methods, scales, clean/attack metrics, hard gates, tie-breakers.
- **coordination_matrix_column_map.v0.1.yaml** — Source file names and column-to-metric mapping (see above).
- **coordination_matrix_spec.v0.1.yaml** — Scoring weights, overall_score alpha, ranking, determinism (sorting, float rounding).

All three are validated by `labtrust validate-policy` against JSON schemas under `policy/schemas/`. The builder validates its output against `coordination_matrix.v0.1.schema.json` before writing.
