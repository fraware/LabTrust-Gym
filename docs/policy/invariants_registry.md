# Invariants and Invariant Registry v1.0

Invariants are defined in `policy/invariants/` (tokens, zones, critical results, **transport**). They specify:

- **Triggers**: which events or conditions invoke the check.
- **Logic**: assertions (e.g. token active, co-location, ACK present, transport temp in band, chain-of-custody).
- **Enforcement**: DENY_ACTION, BLOCK_ACTION, FORENSIC_FREEZE_LOG, etc.
- **Reason codes**: canonical code returned on violation.

The engine evaluates invariants at the appropriate hooks (e.g. pre_action_validate, post_action_log) and returns violations in the step result. The golden runner asserts expected violation tokens in scenario expectations.

## Transport and export in the golden suite

Transport invariants **INV-TRANSPORT-001** (temp in band) and **INV-COC-001** (chain-of-custody: dispatch must have receive or CHAIN_OF_CUSTODY_SIGN) are exercised by the golden suite:

- **GS-TRANSPORT-001**: Happy path dispatch → tick → sign → receive; no violations.
- **GS-TRANSPORT-002**: Temp excursion → BLOCKED with `TRANSPORT_TEMP_EXCURSION` and INV-TRANSPORT-001.
- **GS-COC-003**: Invalid/missing chain-of-custody → BLOCKED with `TRANSPORT_CHAIN_OF_CUSTODY_BROKEN` and INV-COC-001.

Export (receipts and FHIR) is covered by **GS-EXPORT-001**, which runs post-run hooks `EXPORT_RECEIPTS`, `VERIFY_BUNDLE`, `EXPORT_FHIR` after a normal episode and asserts output files exist and the evidence bundle manifest validates. See [Benchmarks](../benchmarks/benchmarks.md#golden-suite-transport-and-export).

---

## Invariant Registry v1.0

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
- **critical_comm_record_fields** (v0.2): — ACK must reference attempt_id and include minimum_record_fields + tier required_fields; else BLOCKED CRIT_ACK_MISSING_FIELDS (INV-CRIT-005).
- **critical_escalation_order** (v0.2): — ESCALATE must append attempt at next tier (tier_index current+1); else BLOCKED CRIT_ESCALATION_OUT_OF_ORDER (INV-CRIT-006).
- **transport_dispatch_receive_or_token**: — DISPATCH_TRANSPORT consignment must have RECEIVE_TRANSPORT at destination or CHAIN_OF_CUSTODY_SIGN (INV-COC-001).
- **transport_temp_in_band**: — TRANSPORT_TICK / RECEIVE_TRANSPORT temp must stay in band or OVERRIDE_RISK_ACCEPTANCE token (INV-TRANSPORT-001).
- **signature_required_valid** (INV-SIG-001): — When strict_signatures enabled, mutating actions must have valid Ed25519 signature over canonical payload; else BLOCKED SIG_MISSING/SIG_INVALID.
- **signature_role_authorized** (INV-SIG-002): — Key role_id must authorize action type (RBAC); else BLOCKED SIG_ROLE_MISMATCH.

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
