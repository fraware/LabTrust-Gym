# Invariant Registry v1.0

The **Invariant Registry** is a strict, machine-readable YAML file that defines invariants compiled into runtime checks. Each entry specifies severity, scope, a logic template (type + parameters), exception hooks, and enforcement hints.

## File and schema

- **Policy file**: `policy/invariants/invariant_registry.v1.0.yaml`
- **JSON Schema**: `policy/schemas/invariant_registry.v1.0.schema.json`
- **Validation**: `labtrust validate-policy` validates the registry against the schema.

## Entry fields

| Field | Required | Description |
|-------|----------|-------------|
| `invariant_id` | Yes | Unique string (e.g. INV-ZONE-001). |
| `title` | Yes | Short title. |
| `description` | No | Longer description. |
| `severity` | Yes | `info` \| `low` \| `med` \| `high` \| `critical`. |
| `scope` | Yes | `specimen` \| `result` \| `device` \| `zone` \| `agent` \| `system`. |
| `signals` | No | List of named signals (PASS/VIOLATION reported in violations list; no new emits vocab required). |
| `logic_template` | Yes | `type`: `transition` \| `state` \| `temporal`; `parameters`: template-specific dict. |
| `exception_hooks` | No | `override_token_types`: list; `allow_when`: expression (optional). |
| `enforcement_hint` | No | `recommend_action`: `none` \| `hold` \| `block` \| `throttle` \| `kill_switch` \| `freeze_zone` \| `forensic_freeze`. |
| `reason_code` | No | Canonical reason code when violated. |
| `triggers` | No | List of action types that trigger the check. |

## Logic template types

Templates are compiled into callable checks in `engine/invariants_runtime.py`. Supported types and parameters:

### state

- **adjacency**: `from_zone`, `to_zone` — MOVE must follow graph edges.
- **colocation**: `action_types` — Device actions require agent in device zone.
- **restricted_door_or_zone**: `door_id`, `zone_id` — OPEN_DOOR/MOVE to restricted requires token.
- **token_active**: — Token refs must be active (INV-TOK-002; expired/consumed).
- **token_not_revoked**: — Token refs must not be revoked (INV-TOK-006).
- **critical_acked**: — RELEASE_RESULT requires ack for critical results.
- **stability_pass**: — START_RUN when specimen within stability windows (INV-STAB-BIOCHEM-001:PASS).
- **cold_chain_ok**: — START_RUN; VIOLATION when temp out of band (INV-ZONE-006).
- **coag_fill_valid**: — ACCEPT_SPECIMEN; citrate + invalid fill => INV-COAG-FILL-001:VIOLATION.
- **token_scope_ok**: — START_RUN_OVERRIDE with valid token_refs => INV-TOK-003:PASS.
- **read_back_confirmed**: — ACK_CRITICAL_RESULT; read_back true => PASS, false => VIOLATION (INV-CRIT-004).

### temporal

- **door_open_duration**: `door_id` — TICK checks door open duration vs max_open_s.

### transition

Reserved for future (e.g. state-transition checks).

## How to add invariants

1. **Add an entry** to `policy/invariants/invariant_registry.v1.0.yaml`:
   - Set `invariant_id`, `title`, `severity`, `scope`.
   - Set `logic_template.type` to one of `state`, `temporal`, `transition`.
   - Set `logic_template.parameters` to the parameters required by the template (see handlers in `invariants_runtime.py`).
   - Optionally set `exception_hooks`, `enforcement_hint`, `reason_code`, `triggers`.

2. **Implement or reuse a handler** in `engine/invariants_runtime.py`:
   - If the template type + parameters (e.g. `state` + `check: "my_check"`) already exist, no code change.
   - Otherwise add a function `_check_my_check(env, event, params)` returning `(passed, reason_code, details)` or `None`, and register it in `_TEMPLATE_HANDLERS`.

3. **Run** `labtrust validate-policy` to ensure the YAML validates against the schema.

4. **Tests**: Add or extend tests in `tests/test_invariants_runtime.py` using a tiny registry fixture if needed.

## Signals and emits

Invariant outcomes are reported in the step **violations** list with `invariant_id` and `status` (PASS/VIOLATION). No new emit types are required in the emits vocab for v1.0; optional `signals` in the registry can document which logical signals the invariant produces.

## Integration with core_env

After each step with `status == ACCEPTED`, the engine calls `invariants_runtime.evaluate(env, event, result)` and merges returned violations with legacy violations by `invariant_id` (registry overwrites legacy for the same id). BLOCKED steps do not run registry checks. Gradually migrate: move checks from core_env into registry templates and remove legacy code; until then, both legacy and registry can produce violations for the same invariant (merge keeps registry version).
