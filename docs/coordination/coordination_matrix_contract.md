# Coordination Matrix Contract v0.1

This contract defines the admissible evidence and invariants for constructing a `CoordinationMatrix.v0.1` artifact. It covers scope and evidence, canonical sources (inputs), and the output schema.

## Scope: live LLM only (non-negotiable)

The Coordination Matrix is defined only for **online live** LLM coordination runs:

- `pipeline_mode = llm_live`
- `allow_network = true`
- `llm_backend_id` in `{openai_live, ollama_live, anthropic_live}`

Any evidence that violates these constraints MUST be rejected.

Rationale: the matrix is intended to compare real-world coordination behavior under latency, cost, and injection pressure. Offline/deterministic pipelines are useful for regression and CI, but they are not admissible evidence for this matrix.

## Admissible evidence

Matrix construction consumes explicit **files**, not open-ended run directories.

Each input file MUST be recorded in the matrix artifact as:

- `path` (repo-relative when possible; absolute paths forbidden)
- `sha256` (hash over raw bytes)
- `bytes` (file size)
- `role` (why the file is used)

The admissible roles and their allowlists are defined by:

- `policy/coordination/coordination_matrix_inputs.v0.1.yaml`

### Required roles

The following roles are required:

- `clean_summary` — `summary_coord.csv`
- `attacked_summary` — `summary_attack.csv` or `pack_summary.csv`
- `injection_policy` — `policy/coordination/injections.v0.2.yaml`
- `column_map` — `policy/coordination/coordination_matrix_column_map.v0.1.yaml`
- `matrix_spec` — `policy/coordination/coordination_matrix_spec.v0.1.yaml`

Optional but recommended:

- `run_provenance` — `metadata.json` and/or `MANIFEST.v0.1.json` when available.

## Live-only invariants (per-row)

For every row included in the matrix:

- `pipeline_mode == llm_live`
- `allow_network == true`
- `llm_backend_id` is allowlisted
- `method_id` is allowlisted

Violations MUST fail matrix construction. Partial acceptance is not allowed for v0.1.

## Path portability rules

Input paths written into the matrix MUST be portable:

- Absolute paths are forbidden
- Home-relative paths (`~/...`) are forbidden
- Builder MUST normalize to repo-relative paths when possible

## Contract gates

A contract-gate test suite MUST:

1. Validate the matrix artifact against `policy/schemas/coordination_matrix.v0.1.schema.json`
2. Validate `coordination_matrix_inputs.v0.1.yaml` against its schema
3. Enforce live-only invariants
4. Enforce internal consistency: ranks unique per scale; recommendations reference existing rows.

This mirrors the philosophy of `risk-register-gate`.

---

## Sources contract (canonical metric sources)

The builder uses exactly one file per role so that matrix inputs remain stable as the codebase evolves ("boring" and durable).

### Canonical sources

| Role | Canonical filename | Search | Required when |
|------|--------------------|--------|---------------|
| Clean coordination summary | `summary_coord.csv` | Under run dir (direct or any subdir, first match by name) | Always for matrix build |
| Attacked coordination summary | `pack_summary.csv` | Under run dir (direct or any subdir, first match by name) | When `attack_metrics` are defined in inputs policy |

The builder **does not** use alternative files (e.g. `summary_v0.2.csv`, `results.json`, `summary_attack.csv`) when the canonical file is present. If the canonical file exists, only that file is read.

If the canonical file is **missing**, the builder fails with a precise error:

- **metric_id** (for each required metric that could not be satisfied)
- **Attempted sources**: list of filenames and whether each was found
- **Required key columns**: e.g. `scale_id`, `method_id` for clean; `scale_id`, `method_id`, `injection_id` for attacked
- **Attempted columns**: for table validation, the header/columns present in the file that was tried (when a file was found but a required metric column was missing)

### Clean summary contract

- **Canonical file**: `summary_coord.csv`
- **Key columns** (required, unique per row): `scale_id`, `method_id`
- **Metric columns**: For each `metric_id` in `coordination_matrix_inputs.v0.1.yaml` under `clean_metrics`, at least one of its **candidates** (from `coordination_matrix_column_map.v0.1.yaml`) must exist in the table. The builder uses the first matching candidate per metric.
- **Duplicate keys**: Rows with the same `(scale_id, method_id)` are not allowed.

Required columns for clean summary: `scale_id`, `method_id`, plus `pipeline_mode`, `allow_network`, `llm_backend_id`. Remaining metric columns are defined by the column map.

### Attacked summary contract

- **Canonical file**: `pack_summary.csv`
- **Semantics**: **Per-injection** table. Each row corresponds to one `(scale_id, method_id, injection_id)` cell.
- **Key columns** (required, unique per row): `scale_id`, `method_id`, `injection_id`
- **Aggregation**: The builder aggregates across injections per `(scale_id, method_id)` using a **worst-case** rule: **lower_is_better** metrics → take the **maximum**; **higher_is_better** metrics → take the **minimum**.
- **Duplicate keys**: Rows with the same `(scale_id, method_id, injection_id)` are not allowed.

Required columns: `scale_id`, `method_id`, `injection_id`, plus `pipeline_mode`, `allow_network`, `llm_backend_id`. Attack metrics are defined by the column map.

Producers (e.g. coordination study runner, coordination security pack) MUST write `summary_coord.csv` and `pack_summary.csv` with these key columns and the metric columns required by the column map. Typical location: `run_dir/summary/summary_coord.csv` or `run_dir/summary_coord.csv`.

### Validation and errors

- **Missing canonical file**: `FileNotFoundError` with canonical filename, run dir, required key columns, and per-metric candidate columns.
- **Missing required key column**: `ValueError` with role, missing column name, and headers present.
- **Duplicate keys**: `ValueError` with role, duplicate key tuple, and row indices.
- **Missing metric column**: `ValueError` with role, metric_id, candidates, and attempted_columns (headers).

### Non-canonical files

If both `summary_coord.csv` and other files (e.g. `results.json`) exist under the run dir, the builder uses **only** `summary_coord.csv` for clean metrics. Non-canonical files are ignored.

---

## Output contract

Target schema: `policy/schemas/coordination_matrix.v0.1.schema.json`  
Canonical fixture: `tests/fixtures/coordination_matrix_fixture.v0.1.json`  
Contract gate: `tests/test_coordination_matrix_contract_gate.py`

### Output filename convention

Tests do **not** require a specific output path. The gate validates any JSON that is loaded and checked against the schema. The fixture is named **`coordination_matrix_fixture.v0.1.json`** (under `tests/fixtures/`). For builder output, a natural convention is **`coordination_matrix.v0.1.json`** (or a path supplied by CLI/config); the artifact must conform to the schema regardless of filename.

### Top-level keys (required)

| Key | Type | Constraint |
|-----|------|------------|
| `version` | string | `"0.1"` |
| `kind` | string | `"coordination_matrix"` |
| `generated_at` | string | minLength 1 (e.g. ISO 8601) |
| `policy_fingerprint` | string | minLength 1 (e.g. `sha256:...`) |
| `spec` | object | see below |
| `inputs` | array | list of input descriptors |
| `scales` | array | list of scale descriptors |
| `rows` | array | minItems 1; main matrix rows |
| `recommendations` | array | per-scale recommendation slots |

### Row/table shape

- **Representation:** One **flat array** `rows`. Each element is one **(scale_id, method_id)** cell. No per-scale blocks or nested tables; ordering is by whatever the builder chooses (contract gate only checks uniqueness of ranks per scale and that recommendation method_ids exist in rows for that scale).
- **Required per row:** `scale_id`, `method_id`, `run_meta`, `metrics`, `scores`, `ranks`, `feasible`.

**spec:** Required `path`, `sha256`, `scope`. **scope** must include `pipeline_mode` enum `["llm_live"]`, `allow_network` boolean `true`, `allowed_llm_backends` and `allowed_methods` non-empty arrays of strings.

**inputs:** Each item required `path`, `sha256`, `role`. **role** enum: `"clean_summary"` | `"attacked_summary"` | `"injection_policy"` | `"column_map"` | `"matrix_spec"` | `"run_provenance"`.

**scales:** Each item required `scale_id` (string), `meta` (object).

**rows[].run_meta:** Required `pipeline_mode`, `allow_network`, `llm_backend_id`, `llm_model_id`, `partner_id`. Constraints: `pipeline_mode` enum `["llm_live"]`; `allow_network` boolean `true`; `llm_model_id` and `partner_id` may be `null`.

**rows[].metrics:** Required `clean`, `attacked`, `degradation`. Each is an object whose values are number | null (metric key → value).

**rows[].scores:** Required `cq_score`, `ar_score`, `penalties`. `cq_score` and `ar_score` in [-1, 1]; `penalties` array of `{ "reason": string, "amount": number in [0, 1] }`.

**rows[].ranks:** Required `cq_rank`, `ar_rank`, `pareto_member`. `cq_rank` and `ar_rank` integer ≥ 1 or `null`; `pareto_member` boolean.

**rows[].feasible:** Required `clean`, `attacked`, `overall`, `reasons`. Booleans for the first three; `reasons` array of strings.

**recommendations:** Each item required `scale_id`, `ops_first`, `sec_first`, `balanced`, `notes`. **ops_first / sec_first / balanced:** each a **pick** object with required `method_id`, `cq_score`, `ar_score` (each `method_id` string or null, scores number or null).

### Determinism / invariants (from contract gate)

- **Live-only:** `spec.scope.pipeline_mode` must be `"llm_live"`, `spec.scope.allow_network` true. Every `rows[].run_meta` must have `pipeline_mode == "llm_live"`, `allow_network == true`, `llm_backend_id` in `spec.scope.allowed_llm_backends`, and `method_id` in `spec.scope.allowed_methods`.
- **Ranks:** Within each `scale_id`, `cq_rank` values (when not null) must be unique; same for `ar_rank`. Ranks must be integers ≥ 1.
- **Recommendations:** For each `scale_id` in `recommendations`, `ops_first.method_id`, `sec_first.method_id`, and `balanced.method_id` must each be either `null` or one of the `method_id` values in `rows` for that `scale_id`.

---

See also: [Coordination matrix](coordination_matrix.md) (user-facing how to run and build).
