# Policy-Driven Enforcement

The **enforcement layer** applies configurable actions when invariant violations occur. It consumes violations emitted by the invariants runtime, matches them against rules in the enforcement map, and applies actions (throttle, kill_switch, freeze_zone, forensic_freeze) with optional escalation (first violation → throttle, repeated → kill_switch or freeze_zone).

## Configuration

- **Policy file**: `policy/enforcement/enforcement_map.v0.1.yaml`
- **Schema**: `policy/schemas/enforcement_map.v0.1.schema.json`
- **Validation**: `labtrust validate-policy` validates the enforcement map.

## Enabling enforcement

Enforcement is **off by default** so the golden suite and existing benchmarks are unchanged. Enable it via env config:

- In `reset(initial_state, ...)`, set `initial_state["enforcement_enabled"] = True`.
- The engine then loads the enforcement map and applies rules on each ACCEPTED step that has violations.

## Rule structure

Each rule has:

- **rule_id**: Unique identifier.
- **match**: Optional filters; all specified fields must match the violation or context.
  - **invariant_id**: Match violations with this `invariant_id`.
  - **severity**: Match by severity (e.g. `critical`, `high`).
  - **scope**: Match by scope (e.g. `zone`, `system`).
- **action**: Default action when the rule matches (type and parameters).
- **escalation**: Optional list of `{ violation_count_min, action }`. The engine tracks violation counts per (agent_id, rule_id) and picks the action for the highest `violation_count_min` that is ≤ current count.

## Action types

| Type              | Parameters       | Description |
|-------------------|------------------|-------------|
| throttle_agent    | duration_s       | Throttle the acting agent for N seconds. |
| kill_switch       | target_type      | Disable agent/device/zone (target from event/context). |
| freeze_zone        | zone_id          | Freeze a zone (e.g. no further moves through door). |
| forensic_freeze   | —                | System-level forensic freeze (audit chain broken). |

## Step output

When enforcement is enabled, the step result includes:

- **enforcements**: List of applied actions, each with:
  - **type**: `throttle_agent` \| `kill_switch` \| `freeze_zone` \| `forensic_freeze`
  - **target** (optional): agent_id or other target
  - **duration_s** (optional): For throttle_agent
  - **zone_id** (optional): For freeze_zone
  - **reason_code** (optional): From the violation
  - **rule_id** (optional): Rule that produced this action

## Audit log

When enforcement runs, each applied action is recorded as an event in the audit log (hash chain), so enforcement is auditable and order is deterministic.

## Implementation

- **Loader**: `policy/loader` loads the enforcement map; schema validation is via `validate-policy`.
- **Engine**: `src/labtrust_gym/engine/enforcement.py` — `EnforcementEngine` loads the map, matches violations, applies escalation, and returns a list of enforcement items. Violation counts are stored per (agent_id, rule_id); call `reset_counts()` on env reset.
- **Integration**: `core_env._finalize_step()` calls the enforcement engine when `enforcement_enabled` is true and merges **enforcements** into the step result; each enforcement is appended to the audit log.

## Tests

- **tests/test_enforcement.py**: Load map, throttle on violation, escalation on repeated violations, deterministic ordering, core_env with enforcement disabled returns empty enforcements.
