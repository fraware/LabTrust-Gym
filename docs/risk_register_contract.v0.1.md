# Risk Register Bundle contract v0.1

This document defines **RiskRegisterBundle.v0.1**: a single JSON artifact that a website (or other consumer) can use to render the full risk register and evidence links without parsing scattered YAMLs at runtime. The bundle is **buildable from repo policy plus run outputs** and is **deterministic** when policy and input run dirs are fixed.

## Scope

- **Bundle version**: `0.1`
- **Schema**: `policy/schemas/risk_register_bundle.v0.1.schema.json`
- **Contract freeze**: Fields and semantics below are stable for v0.1; additive-only changes in future minor versions.

## Bundle content (minimum viable but complete)

### Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bundle_version` | string | Yes | Literal `"0.1"`. |
| `generated_at` | string | No | ISO 8601 timestamp when the bundle was built. Omit for maximum determinism (consumer can rely on `git_commit_hash`). |
| `git_commit_hash` | string | No | Git commit SHA of the repo at build time (provenance). |
| `policy_fingerprints` | object | No | Reuse of existing fingerprint machinery: keys such as `tool_registry`, `rbac_policy`, `coordination_policy`, `memory_policy`, `risk_registry` with string values (e.g. SHA-256 or composite hash). |
| `risks` | array | Yes | One entry per risk from `policy/risks/risk_registry.v0.1.yaml` with crosswalk fields. |
| `controls` | array | Yes | Controls from safety-case claims and/or `policy/golden/security_attack_suite.v0.1.yaml` (control_id, name, description). |
| `evidence` | array | Yes | Aggregated evidence: security suite outputs, coordination study outputs, optional official pack index. |
| `links` | array | No | Pointers to repo-local paths (policy files, docs) and run-local paths (evidence bundle dirs, ui-export zip, figures/tables). |

### Risks (crosswalk)

Each element of `risks[]` has at least:

| Field | Type | Description |
|-------|------|-------------|
| `risk_id` | string | From risk_registry (e.g. `R-TOOL-001`, `R-COMMS-001`). |
| `name` | string | Human-readable name from registry. |
| `risk_domain` | string | Domain for grouping: `tool`, `flow`, `system`, `comms`, `identity`, `data`, `capability`, `operational`. Aligned with registry `category` where applicable; `identity` may be used for spoofing/replay. |
| `applies_to` | array of string | Where the risk applies: `engine`, `online`, `coordination`, `llm_offline`, `llm_live`. Derived from which benchmarks/tasks cover the risk. |
| `claimed_controls` | array of string | `control_id[]` that mitigate this risk (from security suite and/or safety-case mapping). |
| `evidence_refs` | array of string | `evidence_id[]` referencing `evidence[]` entries that provide evidence for this risk. |
| `coverage_status` | string | Derived from method_risk_matrix and security suite: `covered`, `partially_covered`, `uncovered`, `not_applicable`. |
| (optional) | | Registry fields: `description`, `typical_failure_mode`, `mitigation_options`, `suggested_injections`, `primary_metrics`, `severity_hint`, `complexity_hint`. |

### Controls

Each element of `controls[]` has:

| Field | Type | Description |
|-------|------|-------------|
| `control_id` | string | Stable ID (e.g. `CTRL-LLM-SHIELD`, `CTRL-RBAC`). |
| `name` | string | Short name. |
| `description` | string | Optional description. |
| `source` | string | Optional: `security_suite` \| `safety_case`. |

Sourced from:

- **Security attack suite**: `policy/golden/security_attack_suite.v0.1.yaml` `controls[]`.
- **Safety case**: `policy/safety_case/claims.v0.1.yaml` — each claim’s `controls` list (string names) mapped to control_ids where possible; otherwise include as controls with source `safety_case`.

### Evidence

Each element of `evidence[]` has:

| Field | Type | Description |
|-------|------|-------------|
| `evidence_id` | string | Unique ID for reference from `risks[].evidence_refs`. |
| `type` | string | `security_suite` \| `coordination_study` \| `official_pack` \| `safety_case` \| `bundle_verification` \| `other`. |
| `path` | string | Optional. Repo- or run-relative path; empty or omitted for `status=missing` stubs. |
| `label` | string | Optional short label for UI. |
| `status` | string | Optional: `present` (evidence exists) or `missing` (explicit stub when no evidence in scanned runs). |
| `expected_sources` | array | For `status=missing`: e.g. "security suite smoke", "coordination study required_bench". |
| `risk_ids` | array | Optional. Risk IDs this evidence applies to. |
| `artifacts` | array | Optional. `{ path, sha256? }` from MANIFEST when known. |
| `summary` | object | Optional: type-specific summary (e.g. `{ "total": 10, "passed": 9 }` for attack_results). |

Aggregated from run dirs (and optional official pack):

- **Security suite**: `SECURITY/attack_results.json`, `SECURITY/coverage.json`; paths run-relative; summary from attack_results.
- **Coordination study**: `summary/summary_coord.csv`, `PARETO/pareto.json` when present.
- **Safety case**: `SAFETY_CASE/safety_case.json` when present.
- **Bundle verification**: `MANIFEST.v0.1.json` (hashes for reviewer trust).
- **Missing**: If a risk has no evidence in scanned runs, a stub with `status=missing` and `expected_sources` is included so missing evidence is explicit.

### Reproduce (how to reproduce)

Each element of `reproduce[]` links an evidence item to deterministic CLI commands so the UI can show "how to reproduce" without hardcoding:

| Field | Type | Description |
|-------|------|-------------|
| `evidence_id` | string | Links to `evidence[]`.evidence_id. |
| `label` | string | Short label (e.g. Security suite, Coordination study). |
| `commands` | array of string | CLI commands to reproduce this evidence (e.g. `labtrust run-security-suite --out <output_dir> --seed 42`). Empty for missing evidence. |

Generated at bundle build time by evidence type (security_suite, coordination_study, safety_case, official_pack, bundle_verification). Placeholders `<output_dir>`, `<study_spec>` are for user substitution.

### Links

Each element of `links[]` has:

| Field | Type | Description |
|-------|------|-------------|
| `link_id` | string | Optional stable ID. |
| `href` | string | Path: repo-local (e.g. `policy/risks/risk_registry.v0.1.yaml`) or run-local (e.g. `SECURITY/coverage.md`, `ui_bundle.zip`). |
| `label` | string | Human-readable label. |
| `type` | string | `repo_local` \| `run_local`. |

## Determinism

- **Build**: Given identical policy files and identical input run directory layout and content, the bundle JSON (excluding optional `generated_at`) MUST be identical. Sort keys and array order (e.g. risks by risk_id, controls by control_id) MUST be deterministic.
- **Timestamps**: For fully deterministic output, omit `generated_at`; consumer can use `git_commit_hash` and run metadata for provenance.

## Validation

- The bundle MUST validate against `policy/schemas/risk_register_bundle.v0.1.schema.json`.
- Every `evidence_ref` in any `risks[].evidence_refs` MUST reference an `evidence_id` present in `evidence[]`.
- Every `claimed_controls` entry SHOULD reference a `control_id` present in `controls[]`.

## Sufficiency for rendering

The bundle is **sufficient to render a complete risk register** without additional file reads: all risk rows, control names, evidence links, and coverage status are embedded. Optional `links[]` and `path` in evidence allow the UI to resolve run-local or repo-local paths for deep links or downloads.

## Build inputs

| Input | Purpose |
|-------|---------|
| `policy/risks/risk_registry.v0.1.yaml` | `risks[]` content and risk_domain (from category). |
| `policy/coordination/method_risk_matrix.v0.1.yaml` | Per-risk coverage_status (aggregate per risk across methods). |
| `policy/golden/security_attack_suite.v0.1.yaml` | `controls[]`, risk–control–attack mapping; evidence entry for SECURITY/. |
| `policy/safety_case/claims.v0.1.yaml` | Additional controls and claim–control mapping. |
| `policy/coordination/risk_to_injection_map.v0.1.yaml` | Optional: injection coverage for risks. |
| Run dir: `SECURITY/attack_results.json`, `SECURITY/coverage.json` | Evidence entries and optional summary. |
| Run dir: `summary/summary_coord.csv`, `PARETO/pareto.json` | Evidence entries for coordination study. |
| Run dir: `SAFETY_CASE/safety_case.json`, `MANIFEST.v0.1.json` | Evidence entries; MANIFEST used for artifact sha256 when present. |
| Run dir: official pack index (if present) | Evidence entry for official pack. |
| Repo: policy file paths + optional fingerprint computation | `policy_fingerprints`, `links[]` repo_local. |

## CLI

- **export-risk-register** — Primary command: `labtrust export-risk-register --out <dir> [--runs <dir_or_glob> ...] [--include-official-pack <dir>] [--inject-ui-export]`. Writes `<dir>/RISK_REGISTER_BUNDLE.v0.1.json`. Run specs can be paths or globs (e.g. `tests/fixtures/ui_fixtures`, `labtrust_runs/*`). With `--inject-ui-export`, the same bundle is written into each run dir for the UI to load.
- **build-risk-register-bundle** — Writes the same bundle to an explicit file path: `--out <path>`, optional `--run <dir>` repeated.

## Versioning

- **Contract version**: 0.1. Backward-incompatible changes require a new contract version and new schema `$id`.
- **Schema**: `risk_register_bundle.v0.1.schema.json`; bundle payload uses `bundle_version: "0.1"`.
