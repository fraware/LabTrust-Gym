# UI data contract (v0.1)

The UI **must not** depend on raw internal logs or ad-hoc shapes. It consumes **ui-export** output as the primary input. This document specifies expected folder layouts, required files, relationships, and schema version handling.

## Primary input: ui-export bundle

Run:

```bash
labtrust ui-export --run <dir> --out <ui_bundle.zip>
```

The bundle contains normalized, UI-ready JSON:

| File | Description |
|------|-------------|
| **index.json** | Episodes, tasks, baselines; file refs (results path, log path, receipts path) per episode. When the run dir contains coordination pack or lab report output, includes `coordination_artifacts`: list of `{ path, label }`; those files are also included in the zip under `coordination/`. |
| **events.json** | All step outcomes in one array: normalized gate fields (status, blocked_reason_code, violations, emits, token_consumed, t_s, agent_id, action_type, event_id). Optionally chunked by episode in future. |
| **receipts_index.json** | List of receipt locations: task/label → path and list of receipt filenames (e.g. receipt_specimen_S1.v0.1.json). |
| **reason_codes.json** | Full reason code registry (code → namespace, severity, description, etc.) so UI does not parse policy YAML. |

**Acceptance:** UI can depend on ui-export output as primary input, not raw internal logs.

---

## Expected folder layouts (run directories)

`--run <dir>` accepts either a **labtrust_runs** run or a **package-release** output directory.

### 1. labtrust_runs (quick-eval)

Typical path: `labtrust_runs/quick_eval_YYYYMMDD_HHMMSS/`.

| Path | Description |
|------|-------------|
| `throughput_sla.json`, `adversarial_disruption.json`, `multi_site_stat.json` | Results files (schema results.v0.2). One file per task; each may contain multiple episodes. |
| `logs/throughput_sla.jsonl`, `logs/adversarial_disruption.jsonl`, `logs/multi_site_stat.jsonl` | Episode log (JSONL): one line per step; same order as steps in run. |
| `summary.md` | Human-readable summary (optional). |

**Relationships:**

- For each `X.json` in run root, there may be `logs/X.jsonl` (task id derived from filename: e.g. `throughput_sla.json` → task `throughput_sla`).
- Episodes in `X.json` are ordered; the i-th episode corresponds to the same run that produced the lines in `logs/X.jsonl` (when num_episodes is 1, the whole JSONL is one episode).
- No receipts directory in plain quick-eval; `receipts_index.json` in the ui-export will be empty or omit this run’s receipts.

### 2. package-release (paper_v0.1)

Typical path: `<out>/` from `labtrust package-release --profile paper_v0.1 --out <out>`.

| Path | Description |
|------|-------------|
| `_baselines/` | Official baselines: `results/*.json`, `summary.csv`, `summary.md`, `metadata.json`. |
| `_study/` | Study run: `manifest.json`, `results/`, `logs/` (per condition), `figures/`. |
| `_repr/<task>/` | Representative run per task: `episodes.jsonl`, `results.json`. |
| `receipts/<task>/` | Receipts and EvidenceBundle.v0.1 per task (e.g. `receipts/throughput_sla/EvidenceBundle.v0.1/`, `receipts/throughput_sla/receipt_*.v0.1.json`). |
| `FIGURES/`, `TABLES/` | Plots and summary tables. |
| `metadata.json`, `RELEASE_NOTES.md` | Run metadata. |

**Relationships:**

- **Episodes / tasks:** From `_repr/<task>/results.json` and `_repr/<task>/episodes.jsonl`; from `_baselines/results/*.json` (task from filename); from `_study/results/` and `_study/logs/` (condition_ids from manifest).
- **Receipts:** For each `receipts/<task>/`, list `EvidenceBundle.v0.1/*.json` and any `receipt_*.v0.1.json` in `receipts/<task>/`; link to episode by task (and optionally condition_id for study).
- **Baselines:** From `_baselines/results/*.json` and `_baselines/metadata.json`; baseline names from metadata or filenames.

**Inferring relationships:**

- **Task → results:** `results.json` or `<TaskName>.json`; schema version in `schema_version` (e.g. `0.2`).
- **Task → log:** Same directory as results: `episodes.jsonl` or `logs/<TaskName>.jsonl`.
- **Task → receipts:** `receipts/<task>/`; receipt files match `receipt_*.v0.1.json` or live inside `EvidenceBundle.v0.1/`.
- **Event → episode:** Events in `events.json` can carry `episode_key` (e.g. `task` + `episode_index`) so UI can group by episode.

### 3. Run dirs with coordination pack or lab report

When `--run <dir>` is a directory that contains coordination security pack output or a lab report (e.g. from `labtrust run-coordination-security-pack` plus `labtrust build-lab-coordination-report`, or `labtrust run-official-pack --include-coordination-pack` which writes into `coordination_pack/`), ui-export scans for these artifacts and adds them to the bundle.

| Path (relative to run dir) | Description |
|-----------------------------|-------------|
| `pack_summary.csv` | One row per cell (scale x method x injection). |
| `pack_gate.md` | PASS/FAIL/not_supported per cell. |
| `SECURITY/coordination_risk_matrix.csv`, `.md` | Method x injection x phase outcomes. |
| `LAB_COORDINATION_REPORT.md` | Single lab report with scope, decision, artifact table. |
| `COORDINATION_DECISION.v0.1.json`, `.md` | Chosen method per scale. |
| `summary/sota_leaderboard.md`, `method_class_comparison.md` | SOTA and method-class comparison. |

When present, **index.json** includes `coordination_artifacts`: a list of `{ "path": "<rel>", "label": "..." }` for each found file. Paths may be under `coordination_pack/` when the run is an official pack with `--include-coordination-pack`. The same files are included in the zip under the prefix **coordination/** (e.g. `coordination/pack_summary.csv`, `coordination/coordination_pack/LAB_COORDINATION_REPORT.md`) so the UI can link to or load them without reading the raw run dir.

---

## Required files and how to infer relationships

| Need | Source |
|------|--------|
| List of tasks | From result filenames (e.g. `throughput_sla.json`) or from `_repr/`, `_baselines/results/`, `_study/results/`. |
| Episodes per task | From `results.json` / `TaskX.json` → `episodes` array; length = number of episodes. |
| Step-level outcomes | From episode log JSONL; each line = one step. ui-export normalizes these into `events.json` with stable field names. |
| Receipts per task | From `receipts/<task>/` and `EvidenceBundle.v0.1/` contents; list in `receipts_index.json`. |
| Reason code labels | From `reason_codes.json` (exported from policy); key = code, value = { namespace, severity, description, ... }. |

**index.json** (logical shape):

- `ui_bundle_version`: string (e.g. `"0.1"`). Always present.
- `run_type`: `"quick_eval"` | `"package_release"` | `"full_pipeline"`. Always present.
- `tasks`: list of task ids. Always present (may be empty).
- `episodes`: list of episode objects. Always present (may be empty).
- `baselines`: list of baseline ids. Always present (may be empty).
- `coordination_artifacts` (optional): list of `{ "path": "<rel>", "label": "..." }` when run dir contains pack_summary.csv, LAB_COORDINATION_REPORT.md, or related files; paths are relative to run dir; files are also in the zip under `coordination/`.
- `pipeline_mode`, `llm_backend_id`, `llm_model_id`, `allow_network` (optional): present when run is from official pack or full pipeline.
- `receipts_note` (optional): present for `full_pipeline` when there are no receipts (explains why receipts_index is empty).
- `coord_telemetry` (optional): present when episode logs have coord_decisions.jsonl.

**Episode object** (each entry in `episodes`):

- `task`: string. Required.
- `episode_index`: number. Required.
- `episode_key`: string (e.g. `"<task>_<episode_index>"`). Optional but emitted by backend.
- `results_ref`: string (path relative to run dir). Required.
- `log_ref`: string or **null** (path to episode log JSONL, or null when no log). Must accept null for full_pipeline and quick_eval without logs.
- `receipts_ref`: string or **null** (path to receipts dir, or null). Must accept null for runs without receipts.

**Frontend validation:** The UI bundle loader must treat `log_ref` and `receipts_ref` as optional or nullable (string | null). Do not require them to be non-empty strings, or validation will fail for bundles from full_pipeline or LLM live official pack runs.

**events.json**:

- Array of normalized events; each has: `t_s`, `agent_id`, `action_type`, `status`, `blocked_reason_code`, `emits`, `violations`, `token_consumed`, `event_id` (if present), and optional `episode_key` / `task` / `episode_index` for grouping.

**receipts_index.json**:

- Array of `{ "task", "path", "receipt_files": [...] }`; `path` is relative to run or bundle root; `receipt_files` are filenames (e.g. `receipt_specimen_S1.v0.1.json`).

**reason_codes.json**:

- `{ "version": "0.1", "codes": { "<code>": { "namespace", "severity", "description", ... } } }`. Same shape as registry; UI uses it for display and validation.

---

## Schema version handling rules

1. **UI bundle schema:** The ui-export output (index, events, receipts_index, reason_codes) is versioned. Current version: **0.1**. The bundle MAY include a top-level `ui_bundle_version` (e.g. in index.json) so the UI can reject unknown versions.
2. **Results:** Results files follow `results.v0.2` (or v0.3). UI must accept `schema_version` and ignore extra fields; do not assume fields beyond the contract.
3. **Receipts:** Receipt files follow `receipt.v0.1`; EvidenceBundle follows `evidence_bundle_manifest.v0.1`. UI must not rely on internal log shapes—only on ui-export’s **receipts_index.json** and the receipt schema for displayed fields.
4. **Extensible only:** New schema versions (e.g. results.v0.3) add optional fields only; required fields and semantics of v0.2 remain. UI should be tolerant of missing optional fields.
5. **Stable field names:** Normalized gate outcomes in `events.json` use fixed names (status, blocked_reason_code, violations, emits, token_consumed). New gate fields are added as optional keys; existing keys are not renamed or removed in v0.1.

---

## Summary

- **Run layouts:** labtrust_runs (quick_eval_*) and package-release (paper_v0.1) are the two supported run directory shapes.
- **Relationships:** Task → results file, task → log file, task → receipts dir; episodes from results `episodes` array; steps from JSONL → normalized into events.json.
- **Schema rules:** UI bundle v0.1; results v0.2/v0.3 extensible only; stable event field names; reason_codes and receipts_index supplied so UI does not parse policy or raw logs.
- **Acceptance:** UI uses ui-export output as primary input; raw internal logs are not part of the UI contract.
