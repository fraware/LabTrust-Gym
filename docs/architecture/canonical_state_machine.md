# Canonical CoreEnv state machine

Authoritative environment semantics for LabTrust-Gym **CoreEnv** (`src/labtrust_gym/engine/core_env.py`). Derived from dispatch tables, stores, reason codes, and invariants—not from aspirational workflow prose.

Narrative workflow context: [Hospital lab workflow](hospital_lab_workflow.md). High-level components: [Architecture](architecture.md).

## Vocabulary boundary: CoreEnv vs PCS

| Layer | Vocabulary | Authority |
|-------|------------|-----------|
| **CoreEnv** | `action_type`, `status` (`ACCEPTED` / `BLOCKED`), `emits`, `blocked_reason_code`, `violations[].invariant_id`, specimen/QC/transport store statuses | This document; golden runner contract |
| **PCS** | Proof-carrying traces, claims, evidence envelopes, workflow profiles | [PCS index](../pcs/index.md), [PCS trace model](../pcs_trace_model.md), [producer contract](../pcs/producer-contract.md) |

Do **not** treat PCS claim IDs or workflow-profile step names as CoreEnv `action_type` values. PCS may cite CoreEnv transitions as evidence; CoreEnv does not import PCS vocab.

---

## Authoritative state owners

| State variable group | Owner (code) | Notes |
|----------------------|--------------|-------|
| Audit hash chain, `log_frozen` | `AuditLog` / `system_state` | Forensic freeze when chain breaks |
| Agent zone positions, doors | `ZoneState` | Adjacency graph + door open-since |
| Specimen lifecycle | `SpecimenStore` | Reception → accession → accept/hold/reject |
| Device queues | `QueueStore` | Per-device work heads |
| Device run timing (simulated) | `DeviceStore` | Optional `timing_mode: simulated` |
| QC device state + results | `QCStore` | `pass`/`fail`; result `generated`/`held`/`released` |
| Critical notify/ack/escalate | `CriticalStore` | Thresholds + escalation ladder |
| Tokens | `TokenStore` | Mint / consume / revoke / TTL |
| Multi-site consignments | `TransportStore` | Dispatch → tick → receive → CoC |
| RBAC mapping | `rbac_policy` (mutable via `UPDATE_ROSTER`) | Role → allowed actions |
| Reagent stock | `_reagent_stock` | Stockout gates `START_RUN` |
| Clock / RNG | `Clock` / `RNG` | Deterministic when seeded |

Policy overlays resolve at reset via `engine/policy_resolution.py` (effective_policy over files over defaults).

---

## Actor roles

From `policy/rbac/rbac_policy.v0.1.yaml` (agent → role):

| Agent id | Role | Typical actions |
|----------|------|-----------------|
| `A_RECEPTION` | `ROLE_RECEPTION` | Accession, accept/hold/reject |
| `A_RUNNER` | `ROLE_RUNNER` | Move, doors, centrifuge/aliquot, transport |
| `A_PREAN` | `ROLE_PREANALYTICS` | Centrifuge, aliquot |
| `A_ANALYTICS` / `A_OPS_0` | `ROLE_ANALYTICS` | Queue, start run, QC event, generate/release |
| `A_QC` | `ROLE_QC` | `QC_EVENT` |
| `A_SUPERVISOR` | `ROLE_SUPERVISOR` | Tokens, critical notify/ack/escalate, release |
| `A_CLINSCI` | `ROLE_CLINICAL_SCIENTIST` | Dual-approval mint, release |
| `A_SECURITY` | `ROLE_SECURITY_OFFICER` | Doors, tokens |
| `SYSTEM` | `R_SYSTEM_CONTROL` | `UPDATE_ROSTER`, `INJECT_SPECIMEN` (signed) |

RBAC is an early gate: denied actions return `BLOCKED` with `RBAC_ACTION_DENY` (or zone/device variants) **without** domain mutation. Tokens cannot bypass RBAC (GS-RBAC-029).

---

## Step dispatch (actions)

Early dispatch (`_STEP_DISPATCH`, before token_refs consumption for restricted doors):

| Action | Handler |
|--------|---------|
| `TICK` | `_step_tick` |
| `MOVE` | `_step_move` |
| `MINT_TOKEN` | `_step_mint_token` |
| `REVOKE_TOKEN` | `_step_revoke_token` |

Late dispatch (`_STEP_DISPATCH_LATE`):

| Action | Handler |
|--------|---------|
| `OPEN_DOOR` | `_step_open_door` |
| `CENTRIFUGE_START` | `_step_centrifuge_start` |
| `QUEUE_RUN` | `_step_queue_run` |
| `CREATE_ACCESSION` | `_step_create_accession` |
| `CHECK_ACCEPTANCE_RULES` | `_step_check_acceptance_rules` |
| `ACCEPT_SPECIMEN` | `_step_accept_specimen` |
| `HOLD_SPECIMEN` | `_step_hold_specimen` |
| `REJECT_SPECIMEN` | `_step_reject_specimen` |
| `CENTRIFUGE_END` | `_step_centrifuge_end` |
| `ALIQUOT_CREATE` | `_step_aliquot_create` |
| `START_RUN` | `_step_start_run` |
| `START_RUN_OVERRIDE` | `_step_start_run_override` |
| `QC_EVENT` | `_step_qc_event` |
| `GENERATE_RESULT` | `_step_generate_result` |
| `RELEASE_RESULT` | `_step_release_result` |
| `HOLD_RESULT` | `_step_hold_result` |
| `RERUN_REQUEST` | `_step_rerun_request` |
| `RELEASE_RESULT_OVERRIDE` | `_step_release_result_override` |
| `NOTIFY_CRITICAL_RESULT` | `_step_notify_critical_result` |
| `ACK_CRITICAL_RESULT` | `_step_ack_critical_result` |
| `ESCALATE_CRITICAL_RESULT` | `_step_escalate_critical_result` |
| `DISPATCH_TRANSPORT` | `_step_dispatch_transport` |
| `TRANSPORT_TICK` | `_step_transport_tick` |
| `RECEIVE_TRANSPORT` | `_step_receive_transport` |
| `CHAIN_OF_CUSTODY_SIGN` | `_step_chain_of_custody_sign` |

Outside those tables (runtime control, always signed): `UPDATE_ROSTER`, `INJECT_SPECIMEN`. Unknown `action_type` falls through to `_step_default` (audit-only accept).

Transition-level tests: `tests/test_core_env_transitions.py` (every `_STEP_DISPATCH` / `_STEP_DISPATCH_LATE` action).

---

## Domain status machines

### Specimen (`SpecimenStore`)

```text
arrived_at_reception
        │ CREATE_ACCESSION
        ▼
   accessioning
        │ ACCEPT_SPECIMEN (rules may auto HOLD/REJECT)
        ├──────────────► accepted
        ├──────────────► held      (HOLD_SPECIMEN / citrate underfill)
        └──────────────► rejected  (ID mismatch, leak, …)
```

Terminal for reception lane: `held` / `rejected` (no further accept without new inject). Downstream analytics use `accepted` specimens/aliquots.

### QC result (`QCStore`)

```text
(create via GENERATE_RESULT) → generated → held | released
```

Device QC state: `pass` | `fail`. Fail gates `RELEASE_RESULT` (`QC_FAIL_ACTIVE`).

### Transport (`TransportStore`)

```text
DISPATCH → in_transit → (TRANSPORT_TICK) → RECEIVE → arrived
                              │
                              └─ CHAIN_OF_CUSTODY_SIGN (CoC flag)
```

### Audit / freeze

```text
append events → hash chain OK
broken chain → log_frozen=true → every subsequent step BLOCKED (AUDIT_CHAIN_BROKEN)
```

---

## Preconditions / postconditions (summary)

Per-action detail is enforced in handlers; the table below is the inspectable contract surface. Full golden scripts: `policy/golden/golden_scenarios.v0.1.yaml`.

| Action | Key preconditions | Success postcondition (typical) | Common BLOCKED codes |
|--------|-------------------|---------------------------------|----------------------|
| `TICK` | Not frozen | Clock/door duration checks; may emit door alarms | `AUDIT_CHAIN_BROKEN` |
| `MOVE` | Adjacent zones; restricted biohazard needs token | Agent/specimen zone updated | `RC_ILLEGAL_MOVE`, `RBAC_RESTRICTED_ENTRY_DENY` |
| `MINT_TOKEN` | Dual-approval rules for type | Token ACTIVE | `INV-TOK-001`, dual-approval violation |
| `REVOKE_TOKEN` | Role allows | Token revoked | RBAC |
| `OPEN_DOOR` | Restricted airlock needs `TOKEN_RESTRICTED_ENTRY` | Door open_since set | `RBAC_RESTRICTED_ENTRY_DENY` |
| `CENTRIFUGE_START` | Agent colocated with device | Run start accepted | `RC_DEVICE_NOT_COLOCATED` |
| `QUEUE_RUN` | Known device; valid payload; unique work_id | Enqueued | `RC_QUEUE_*`, `RC_DEVICE_UNKNOWN` |
| `CREATE_ACCESSION` | Specimen exists at reception | Status `accessioning` | (missing id → default accept path) |
| `CHECK_ACCEPTANCE_RULES` | Specimen id | Acceptance flags recorded | — |
| `ACCEPT_SPECIMEN` | Specimen present | accept / hold / reject emit | Domain emit path (often ACCEPTED with REJECT/HOLD emit) |
| `HOLD_SPECIMEN` | Non-empty `reason_code` | Status `held` | `AUDIT_MISSING_REASON_CODE` |
| `REJECT_SPECIMEN` | Specimen present | Status `rejected` | — |
| `CENTRIFUGE_END` | Specimen ids | `separated_ts_s` set | — |
| `ALIQUOT_CREATE` | specimen + aliquot ids | Aliquot recorded | — |
| `START_RUN` | Colocation; queue/stability/temp/reagent | Run registered | `RC_DEVICE_NOT_COLOCATED`, `TIME_EXPIRED`, `TEMP_OUT_OF_BAND`, `RC_QUEUE_*`, stockout |
| `START_RUN_OVERRIDE` | Valid override token refs | Run + token consumed | Token validity / colocation |
| `QC_EVENT` | device_id | Device QC state set | — |
| `GENERATE_RESULT` | result_id | Result `generated`; optional classify | — |
| `RELEASE_RESULT` | QC pass; critical ACK if CRIT | Result `released` | `QC_FAIL_ACTIVE`, `CRIT_NO_ACK` |
| `HOLD_RESULT` | result_id | Result `held` | — |
| `RERUN_REQUEST` | Role | Emit only | — |
| `RELEASE_RESULT_OVERRIDE` | Valid drift/override token | Released + disclaimer flag | Token / QC gates |
| `NOTIFY_CRITICAL_RESULT` | Mode allowed | Notify recorded | `CRIT_MODE_NOT_ALLOWED` |
| `ACK_CRITICAL_RESULT` | Required ACK fields | ACK recorded | `CRIT_ACK_MISSING_FIELDS` |
| `ESCALATE_CRITICAL_RESULT` | Escalation order | Escalate recorded | `CRIT_ESCALATION_OUT_OF_ORDER` |
| `DISPATCH_TRANSPORT` | Allowed route | Consignment `in_transit` | `TRANSPORT_ROUTE_FORBIDDEN` |
| `TRANSPORT_TICK` | Active consignments | Arrival/temp checks | (violations on excursion) |
| `RECEIVE_TRANSPORT` | Valid consignment; temp/CoC OK | `arrived` | `TRANSPORT_TEMP_EXCURSION`, `TRANSPORT_CHAIN_OF_CUSTODY_BROKEN` |
| `CHAIN_OF_CUSTODY_SIGN` | Consignment | CoC signed | CoC broken |

Early gates (before handlers): tool registry, RBAC, agent capabilities, signatures (`strict_signatures`), device colocation for start-run.

---

## Invariants

Registry files under `policy/invariants/`:

- `invariant_registry.v1.0.yaml` (core)
- `invariant_registry.v1.0.zones.yaml`
- `invariant_registry.v1.0.tokens.yaml`
- `invariant_registry.v1.0.critical_results.yaml`

Runtime: `InvariantsRuntime` runs on **ACCEPTED** steps only (`_finalize_step`). Examples: `INV-ZONE-001` (illegal move), `INV-ZONE-002` (colocation), `INV-TOK-*`, `INV-CRIT-*`, `INV-STAB-*`, `INV-TRANSPORT-001`, `INV-COC-001`, `INV-COAG-FILL-001`.

---

## Terminal states and points of no return

| Point of no return | Effect |
|--------------------|--------|
| Specimen `rejected` | Reception path closed for that specimen id |
| Specimen `held` (hard-stop underfill) | Non-overridable hold (GS-003) |
| Result `released` | Downstream release path complete for that result |
| Token `CONSUMED` / `REVOKED` | Cannot reuse (GS-012, GS-013) |
| `log_frozen` | **All** further steps BLOCKED (`AUDIT_CHAIN_BROKEN`) |
| Zone kill-switch (door open too long) | Zone frozen; enforcement emits |

---

## Failure reason codes

Canonical registry: `policy/reason_codes/reason_code_registry.v0.1.yaml`.

Namespaces used by CoreEnv transitions include: `ID_*`, `INT_*`, `CNT_*`, `REQ_*`, `TIME_*` / `TIME_EXPIRED`, `TEMP_OUT_OF_BAND`, `QC_*`, `CRIT_*`, `RBAC_*`, `AUD*` / `AUDIT_*`, `TRANSPORT_*`, `SIG_*`, `RC_QUEUE_*`, `RC_DEVICE_*`, `RC_ILLEGAL_MOVE`, token invariant ids as blocked codes.

PCS reason codes (`policy/pcs/reason_codes.yaml`) are a **separate** vocabulary for PCS workflows.

---

## BLOCKED-must-not-mutate contract

**Contract:** When `status == "BLOCKED"`, world stores (specimens, QC results, zones/agents, queues, devices, transport consignments, tokens) must not change. The audit log may grow on **domain** BLOCKED paths that call `audit.append` before returning; **early gates** (frozen log, RBAC, signatures, tools) typically return `_blocked_result` with `hashchain_snapshot()` and do **not** append.

Documented in [Architecture](architecture.md), [Hospital lab workflow](hospital_lab_workflow.md), and golden `runner_contract` semantics.

Tests: `tests/test_core_env_transitions.py` (`test_blocked_hold_specimen_does_not_mutate`, `test_blocked_rbac_does_not_mutate_specimen`) and `tests/test_specimens.py`.

---

## Related coverage

Hazard × scenario matrix: [`policy/coverage/hazard_coverage_matrix.v0.1.yaml`](../../policy/coverage/hazard_coverage_matrix.v0.1.yaml). Program overview: [Scientific credibility](../benchmarks/scientific_credibility.md).
