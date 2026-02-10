# Coordination policy (risk registry and method registry)

This document describes the policy-as-data **Risk Registry**, **Coordination Method Registry**, **Method-Risk Coverage Matrix**, and **Coordination Study Spec** used so benchmarks can (a) declare risks from policy, (b) map method to risk coverage, and (c) enforce deterministic, schema-validated experiment matrices. No frozen contracts (runner output, queue, invariant registry, enforcement map) are changed.

## Overview

| Policy area | Location | Schema | Purpose |
|-------------|----------|--------|---------|
| Risk registry | `policy/risks/risk_registry.v0.1.yaml` | `policy/schemas/risk_registry.v0.1.schema.json` | Declarative risk catalog: risk_id, category, primary_metrics, suggested_injections. |
| Coordination methods | `policy/coordination/coordination_methods.v0.1.yaml` | `policy/schemas/coordination_methods.v0.1.schema.json` | Methods to compare: method_id, coordination_class, known_weaknesses (risk_id), required_controls. |
| Method-risk matrix | `policy/coordination/method_risk_matrix.v0.1.yaml` | `policy/schemas/method_risk_matrix.v0.1.schema.json` | Coverage per (method_id, risk_id): coverage, rationale, required_bench. |
| Coordination study spec | `policy/coordination/coordination_study_spec.v0.1.yaml` | `policy/schemas/coordination_study_spec.v0.1.schema.json` | Experiment matrix: study_id, scales, methods, risks, injections, episodes_per_cell, seed_base. |
| Scale configs | `policy/coordination/scale_configs.v0.1.yaml` | (optional schema) | Named scale configs (e.g. corridor_heavy, small_smoke) for coord_scale/coord_risk. |
| Resilience scoring | `policy/coordination/resilience_scoring.v0.1.yaml` | `policy/schemas/resilience_scoring.v0.1.schema.json` | Component weights (perf, safety, security, coordination), normalization ranges, missing-metric behavior for resilience_score. |

All of these are validated by `labtrust validate-policy` where a schema exists. Loading and fingerprinting are deterministic (no ambient randomness). Study specs may list **legacy injection IDs** (e.g. `inj_tool_selection_noise`, `inj_prompt_injection`); these are implemented as **NoOpInjector** (passthrough, no mutation) so the study runner completes all cells without failing. Implemented **INJ-*** injection IDs (e.g. INJ-COMMS-POISON-001, INJ-ID-SPOOF-001) use the full risk injectors.

## Risk registry

**File:** `policy/risks/risk_registry.v0.1.yaml`

**Top-level key:** `risk_registry` with `version` and `risks` (array).

Each risk entry has:

- **risk_id** (string, stable): e.g. `R-TOOL-001`, `R-SYS-001`.
- **name**: Short human-readable name.
- **category**: One of `tool`, `capability`, `flow`, `system`, `data`, `comms`.
- **description**: One to three lines.
- **typical_failure_mode** (optional): Short description.
- **mitigation_options** (optional): List of strings.
- **suggested_injections** (optional): List of `injection_id` strings used in study specs.
- **primary_metrics** (optional): List of metric keys (see Metrics naming below).
- **severity_hint** (optional): `low`, `medium`, or `high`.
- **complexity_hint** (optional): `low`, `medium`, or `high`.

**API:** `load_risk_registry(path)` returns `RiskRegistry` (dataclass with `version` and `risks: Dict[str, Dict]`). `get_risk(registry, risk_id)` returns the risk entry dict or `None`.

## Coordination method registry

**File:** `policy/coordination/coordination_methods.v0.1.yaml`

**Top-level key:** `coordination_methods` with `version` and `methods` (array).

Each method entry has:

- **method_id** (string): e.g. `centralized_planner`, `llm_constrained`.
- **name**: Human-readable name.
- **coordination_class**: One of `centralized`, `hierarchical`, `market`, `decentralized`, `swarm`, `learning`, `llm`.
- **scaling_knobs** (optional): List of strings (e.g. `num_agents`, `num_sites`, `num_devices`, `specimen_rate`).
- **known_weaknesses** (optional): List of `risk_id` from the risk registry.
- **required_controls** (optional): List of strings (e.g. `signed_actions`, `RBAC`, `rate_limit`, `message_auth`).
- **compatible_injections** (optional): List of `injection_id`.
- **default_params** (optional): Object (small set of optional params).

**API:** `load_coordination_methods(path)` returns `Dict[str, Dict]` (method_id to entry).

## Method-risk matrix

**File:** `policy/coordination/method_risk_matrix.v0.1.yaml`

**Top-level key:** `method_risk_matrix` with `matrix_id`, `version`, and `cells` (array).

Each cell has:

- **method_id**, **risk_id**: References to method and risk registries.
- **coverage**: One of `not_applicable`, `covered`, `partially_covered`, `uncovered`.
- **rationale** (optional): Short string.
- **required_bench** (optional, bool): If true, this (method, risk) must be benchmarked in coordination studies.

**API:** `load_method_risk_matrix(path)` returns a dict with `matrix_id`, `version`, and `cells`. `get_required_bench_cells(matrix)` returns the list of cells where `required_bench` is true. The external reviewer script and **coverage gate** (`labtrust_gym.studies.coverage_gate.check_summary_coverage`) ensure every required_bench (method_id, risk_id) has at least one row in `summary_coord.csv`; set `LABTRUST_STRICT_COVERAGE=1` to exit with failure when any required cell is missing.

## Coordination study spec

**File:** `policy/coordination/coordination_study_spec.v0.1.yaml` (example or concrete study).

**Required top-level:** `study_id`, `seed_base`, `episodes_per_cell`.

**Optional:**

- **scales**: List of scale configs: `name` (one of `num_agents`, `num_sites`, `num_devices`, `arrival_rate`, `horizon_steps`) and `values` (array).
- **methods**: List of `method_id`.
- **risks**: List of `risk_id` (subset).
- **injections**: List of objects with `injection_id`, optional `intensity`, optional `seed_offset`.

**API:** `load_coordination_study_spec(path)` returns the full spec dict. Studies are data-driven: the Cartesian product of scales/methods/risks/injections (as implemented by the runner) defines the experiment matrix. Seeds are derived from `seed_base` and per-injection `seed_offset` for determinism.

## Metrics naming

Metric keys referenced in risk registry `primary_metrics` and in results:

- **perf.** `throughput`, `mean_tat`, `p95_tat`, `makespan`
- **comm.** `msg_count`, `p95_latency_ms`, `drop_rate`
- **safety.** `violations_total`, `blocks_total`, `override_count`
- **sec.** `attack_success_rate`, `detection_latency_steps`, `containment_time_steps`
- **cost.** `total_tokens`, `estimated_cost_usd` (when LLM used)
- **robustness.** `regret_vs_nominal`, `resilience_score`

## Validation and determinism

- **Validation:** All four policy files are included in `POLICY_FILES_WITH_SCHEMAS` and validated by `labtrust validate-policy` against their JSON schemas.
- **Determinism:** Loading these files does not introduce randomness. Same file content yields identical in-memory structure; fingerprinting (e.g. for policy pack) uses canonical JSON and is stable across runs.
- **Backward compatibility:** Schemas use optional fields where appropriate; new optional fields can be added in future versions without breaking existing consumers.

## Reason codes and emits

The risk and coordination registries do not define new engine emits or reason codes. They are declarative: benchmarks and study runners reference `risk_id`, `method_id`, and `injection_id` from these files. Linking reason codes (e.g. for "blocked due to risk") to risk_id can be added in a future extension if needed.

## See also

- [Coordination matrix](coordination_matrix.md): matrix inputs, column map, and spec (llm_live only; not used for offline pipelines).
- [Frozen contracts](frozen_contracts.md): runner output, queue, invariant registry, enforcement map.
- [Policy validation](api/index.md): `labtrust validate-policy` and schema mapping.
- [Metrics contract](metrics_contract.md): benchmark results and summary semantics.
