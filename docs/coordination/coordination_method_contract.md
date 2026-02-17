# Coordination Method Contract v0.1

Strict interface and telemetry schema for coordination method plug-ins so all methods (centralized, hierarchical, market, gossip, swarm, LLM, MARL kernels) are first-class and comparable.

## Design

- **Do not break existing methods**: wrap/adapt them; contract output is produced by the runner from method output and harness telemetry.
- **Deterministic mode** is required for official baselines; same seed and config yield identical `coord_decisions.jsonl`.
- **Proof logging**: every coord_scale/coord_risk episode run writes `coord_decisions.jsonl` (one JSONL line per step, validated against the contract schema when `LABTRUST_STRICT_COORD_CONTRACT=1`).

## Contract schema (one timestep)

Schema: `policy/schemas/coord_method_output_contract.v0.1.schema.json`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| method_id | string | yes | Registry method_id (e.g. centralized_planner, market_auction). |
| t_step | integer | yes | Simulation step index (0-based). |
| actions | array | yes | Per-agent actions; each item: agent_id, action_index, optional action_type, args. |
| view_age_ms | number | no | Max or mean view age in ms (staleness) for this step. |
| view_age_ms_per_agent | object | no | Per-agent view age in ms. |
| plan_time_ms | number \| null | no | Planning/decision time in ms if measured. |
| invariants_considered | string[] | no | Invariant IDs considered (e.g. INV-COC-001). |
| safety_shield_applied | boolean | no | True if a safety shield (e.g. simplex) overrode or corrected actions. |
| safety_shield_details | object \| null | no | Overrides count, reason codes, etc. |

## Adapter layer

- **CoordinationMethod** (existing): `propose_actions(obs, infos, t)` or `step(context)` returns per-agent actions; kernel-composed methods also return `CoordinationDecision` (allocation/schedule/route hashes).
- **CoordDecision** (contract): One record per step built by the runner from method_id, t_step, actions, view ages (from BlackboardHarness/check_staleness), optional plan_time_ms, invariants_considered (from policy or []), and safety_shield from method’s `last_shield_emits` when present.
- **telemetry** (`src/labtrust_gym/baselines/coordination/telemetry.py`): Canonical serialization (sort_keys JSON), schema validation against `coord_method_output_contract.v0.1.schema.json`, and building the contract record from runner data.

## Runner behaviour

- For coord_scale/coord_risk with a coordination method and when `log_path` is set, the runner opens `coord_decisions.jsonl` in the same directory as the episode log and appends one line per step (canonical JSON).
- When **LABTRUST_STRICT_COORD_CONTRACT=1**: each record is validated against the contract schema before append; on validation failure the run fails (e.g. missing required fields or invalid types).
- When the env var is unset, records are still written and optionally validated in tests; strict mode is for CI and official baseline runs.

## Proof from repo

- Each coordination run directory (e.g. study cell output or `_repr`/receipts run) that contains an episode log also contains **coord_decisions.jsonl** for that episode when coordination was used.
- **ui-export**: coordination telemetry can be included in the UI bundle under a stable key (e.g. `events.json` or a dedicated `coord_telemetry.jsonl` reference) so the UI can show per-step method_id, staleness, and shield applied.

## See also

- `docs/coordination_methods.md` for method registry and kernel composition.
- `policy/schemas/coord_method_output_contract.v0.1.schema.json` for the full JSON Schema.
