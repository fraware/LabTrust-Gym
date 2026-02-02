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
| **index.json** | Episodes, tasks, baselines; file refs (results path, log path, receipts path) per episode. |
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
| `TaskA.json`, `TaskD.json`, `TaskE.json` | Results files (schema results.v0.2). One file per task; each may contain multiple episodes. |
| `logs/TaskA.jsonl`, `logs/TaskD.jsonl`, `logs/TaskE.jsonl` | Episode log (JSONL): one line per step; same order as steps in run. |
| `summary.md` | Human-readable summary (optional). |

**Relationships:**

- For each `X.json` in run root, there may be `logs/X.jsonl` (task name derived from filename: e.g. `TaskA.json` → task `TaskA`).
- Episodes in `X.json` are ordered; the i-th episode corresponds to the same run that produced the lines in `logs/X.jsonl` (when num_episodes is 1, the whole JSONL is one episode).
- No receipts directory in plain quick-eval; `receipts_index.json` in the ui-export will be empty or omit this run’s receipts.

### 2. package-release (paper_v0.1)

Typical path: `<out>/` from `labtrust package-release --profile paper_v0.1 --out <out>`.

| Path | Description |
|------|-------------|
| `_baselines/` | Official baselines: `results/*.json`, `summary.csv`, `summary.md`, `metadata.json`. |
| `_study/` | Study run: `manifest.json`, `results/`, `logs/` (per condition), `figures/`. |
| `_repr/<task>/` | Representative run per task: `episodes.jsonl`, `results.json`. |
| `receipts/<task>/` | Receipts and EvidenceBundle.v0.1 per task (e.g. `receipts/TaskA/EvidenceBundle.v0.1/`, `receipts/TaskA/receipt_*.v0.1.json`). |
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

---

## Required files and how to infer relationships

| Need | Source |
|------|--------|
| List of tasks | From result filenames (e.g. `TaskA.json`) or from `_repr/`, `_baselines/results/`, `_study/results/`. |
| Episodes per task | From `results.json` / `TaskX.json` → `episodes` array; length = number of episodes. |
| Step-level outcomes | From episode log JSONL; each line = one step. ui-export normalizes these into `events.json` with stable field names. |
| Receipts per task | From `receipts/<task>/` and `EvidenceBundle.v0.1/` contents; list in `receipts_index.json`. |
| Reason code labels | From `reason_codes.json` (exported from policy); key = code, value = { namespace, severity, description, ... }. |

**index.json** (logical shape):

- `run_type`: `"quick_eval"` | `"package_release"`.
- `tasks`: list of task ids.
- `episodes`: list of `{ "task", "episode_index", "results_ref", "log_ref", "receipts_ref" }` (refs = paths relative to run dir or keys into bundle).
- `baselines`: list of baseline ids present in the run (if any).

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
