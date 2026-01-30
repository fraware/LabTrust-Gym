# LabTrust-Gym — Current State of the Repo

This document reports what is implemented, what is not, and what remains to reach the north star (pip-installable multi-agent lab environment with trust skeleton, benchmarks, and baselines).

**Last updated:** reflects the codebase as of the latest implementation pass (policy validation, golden runner, hashchain, tokens, zones, specimens, QC, critical results, catalogue/stability, co-location).

---

## 1. Repo layout vs design

### 1.1 Implemented and aligned with design

| Area | Status | Notes |
|------|--------|--------|
| **Root metadata** | ✅ | README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, LICENSE (Apache-2.0), .gitignore |
| **CI** | ✅ | `.github/workflows/ci.yml`, `release.yml`; ruff format/check, mypy, pytest, policy validation |
| **Policy tree** | ✅ | `policy/schemas/`, `policy/emits/`, `policy/invariants/`, `policy/tokens/`, `policy/reason_codes/`, `policy/zones/`, `policy/catalogue/`, `policy/stability/`, `policy/equipment/`, `policy/critical/`, `policy/golden/` |
| **Source tree** | ✅ | `src/labtrust_gym/` with `engine/`, `policy/`, `runner/`, `cli/`, `version.py` |
| **Tests** | ✅ | `tests/` with test_policy_validation, test_golden_suite, test_hashchain, test_tokens, test_zones, test_specimens, test_qc, test_critical, test_stability, test_catalogue, test_emits_and_reason_codes |
| **Examples** | ⚠️ | `examples/minimal_random_policy_agent.py` only; no scripted_ops_agent, scripted_runner_agent yet |
| **Docs** | ⚠️ | `docs/architecture.md`, `policy_pack.md`, `threat_model.md`, `invariants.md` exist but are brief |

### 1.2 Not present (from original directory spec)

- **Engine:** `state.py`, `event.py`, `clock.py`, `rng.py`, `devices.py`, `queueing.py`, `errors.py` — not created as separate modules; logic lives in `core_env.py` and domain modules (`audit_log`, `zones`, `specimens`, `qc`, `critical`, `catalogue_runtime`, `tokens_runtime`).
- **Policy schemas:** Only `runner_output_contract.v0.1.schema.json` and `test_catalogue.schema.v0.1.json` exist under `policy/schemas/`. No dedicated JSON schemas yet for tokens, invariants, reason codes, zones, critical results, equipment.
- **Examples:** `scripted_ops_agent.py`, `scripted_runner_agent.py` are not implemented.

---

## 2. What was implemented

### 2.1 Policy loading and validation

- **`src/labtrust_gym/policy/loader.py`** — Loads YAML/JSON from policy paths; validates JSON against JSON Schema when a schema path is given.
- **`src/labtrust_gym/policy/validate.py`** — Used by CLI; validates runner output contract schema file, emits vocab `canonical_set`, golden scenarios parse and required fields.
- **CLI** — `labtrust validate-policy` runs full policy validation (schemas, emits, golden YAML).
- **Tests** — `tests/test_policy_validation.py` fails if any required file is missing or invalid.

### 2.2 Golden runner and harness

- **`src/labtrust_gym/runner/adapter.py`** — `LabTrustEnvAdapter` interface (reset, step, query).
- **`src/labtrust_gym/runner/golden_runner.py`** — Scenario execution, assertions (status, emits, violations, blocked_reason_code, token_consumed, state_assertions, hashchain), output matches runner contract shape.
- **`src/labtrust_gym/runner/emits_validator.py`** — `load_emits_vocab(path)`, `validate_emits(emits, allowed, event_id)`; GoldenRunner enforces emits vocab (unknown emits ⇒ AssertionError).
- **`tests/test_golden_suite.py`** — Loads runner output contract schema, validates step output via jsonschema; fails if any scenario failed; gated by `LABTRUST_RUN_GOLDEN=1`; uses placeholder adapter when env var unset (tests skipped).

### 2.3 Audit hashchain and forensic freeze

- **`src/labtrust_gym/engine/audit_log.py`** — Canonical event serialization (deterministic), SHA-256 hash chain, append(event) → head_hash, last_event_hash, length; fault injection `break_hash_prev_on_event_id`; chain break → forensic freeze.
- **`src/labtrust_gym/engine/core_env.py`** — Minimal engine: reset(initial_state, deterministic, rng_seed), step(event) returns contract (status, emits, violations, blocked_reason_code, token_consumed, hashchain); once log_frozen, all steps BLOCKED with AUDIT_CHAIN_BROKEN; FORENSIC_FREEZE_LOG emitted at freeze.
- **query(expr)** — `system_state('log_frozen')`, `last_reason_code_system`.
- **Tests** — `tests/test_hashchain.py` (unit + integration); GS-022 passes when `LABTRUST_RUN_GOLDEN=1` with real engine.

### 2.4 Emits and reason codes (strict validation)

- **`policy/emits/emits_vocab.v0.1.yaml`** — Canonical set of allowed emit types.
- **`src/labtrust_gym/policy/emits.py`** — Load vocab, validate engine step emits.
- **`policy/reason_codes/reason_code_registry.v0.1.yaml`** — Starter registry (AUDIT_CHAIN_BROKEN, AUDIT_MISSING_REASON_CODE, RC_DEVICE_NOT_COLOCATED, ID_MISMATCH, CNT_CITRATE_FILL_INVALID, INT_LEAKING, QC_FAIL_ACTIVE, CRIT_NO_ACK, TIME_EXPIRED, TEMP_OUT_OF_BAND, RBAC_RESTRICTED_ENTRY_DENY, etc.).
- **`src/labtrust_gym/policy/reason_codes.py`** — Load registry, validate code exists, lookup.
- **GoldenRunner** — When `LABTRUST_STRICT_REASON_CODES=1`, blocked_reason_code and action reason_code must be in registry.
- **Tests** — `tests/test_emits_and_reason_codes.py` (strict and non-strict modes).

### 2.5 Token lifecycle and dual approval

- **`src/labtrust_gym/policy/tokens.py`** — Token dataclass, dual-approval validation (two distinct approvers/keys), lifecycle (ACTIVE → CONSUMED/REVOKED/EXPIRED).
- **`src/labtrust_gym/engine/tokens_runtime.py`** — Token store: mint_token, consume_token, revoke_token, is_valid(token_id, t_s); replay protection (consumed/expired/revoked invalid).
- **Engine** — MINT_TOKEN, REVOKE_TOKEN; any action with token_refs validated; consumed on use.
- **Tests** — `tests/test_tokens.py`; GS-010–GS-013 pass under `LABTRUST_RUN_GOLDEN=1`.

### 2.6 Zone graph and doors

- **`policy/zones/zone_layout_policy.v0.1.yaml`** — Zones, graph_edges, doors (including D_RESTRICTED_AIRLOCK), device_placement (device_id → zone_id).
- **`src/labtrust_gym/engine/zones.py`** — ZoneState: adjacency, agent positions, door open_since, tick() for door-open-too-long → ALARM, KILL_SWITCH_ZONE, zone frozen; move(), open_door(); build_device_zone_map(device_placement), get_default_device_zone_map().
- **Engine** — MOVE (adjacency; restricted zone requires token); OPEN_DOOR (restricted requires TOKEN_RESTRICTED_ENTRY); TICK door breach.
- **query(expr)** — `zone_state('Z_RESTRICTED_BIOHAZARD')` → 'frozen' | 'normal'.
- **Tests** — `tests/test_zones.py`; GS-008, GS-009, GS-020 pass.

### 2.7 Reception / specimen acceptance

- **`src/labtrust_gym/engine/specimens.py`** — SpecimenStore: state machine, templates (S_BIOCHEM_OK, S_COAG_OK); CREATE_ACCESSION, CHECK_ACCEPTANCE_RULES, ACCEPT_SPECIMEN, REJECT_SPECIMEN, HOLD_SPECIMEN; ID mismatch → reject (ID_MISMATCH); leaking → reject (INT_LEAKING); citrate underfill → hold (CNT_CITRATE_FILL_INVALID); HOLD_SPECIMEN without reason_code → BLOCKED AUDIT_MISSING_REASON_CODE.
- **Engine** — All acceptance actions wired; BLOCKED does not mutate specimen state.
- **Tests** — `tests/test_specimens.py`; GS-003, GS-004, GS-005, GS-021 pass.

### 2.8 QC and result gating

- **`src/labtrust_gym/engine/qc.py`** — QCStore: device qc_state, run–device mapping, results (status, flags); QC_EVENT, RERUN_REQUEST, START_RUN, GENERATE_RESULT, RELEASE_RESULT, HOLD_RESULT, RELEASE_RESULT_OVERRIDE (TOKEN_QC_DRIFT_OVERRIDE, QC_DRIFT_DISCLAIMER_REQUIRED).
- **Engine** — If device qc_state == fail, RELEASE_RESULT BLOCKED (QC_FAIL_ACTIVE); after QC pass, release allowed; drift override path with token and flag.
- **query(expr)** — `result_status('...')`, `result_flags('...')`.
- **Tests** — `tests/test_qc.py`; GS-014, GS-015 pass.

### 2.9 Critical results

- **`policy/critical/critical_thresholds.v0.1.yaml`** — Placeholder thresholds (K, Na, Hb, INR, etc.).
- **`src/labtrust_gym/engine/critical.py`** — Classify CRIT_A/CRIT_B/none; CriticalStore: comm records (notify/ack), notification_mode_required; NOTIFY_CRITICAL_RESULT, ACK_CRITICAL_RESULT (read_back_confirmed → INV-CRIT-004 PASS/VIOLATION), ESCALATE_CRITICAL_RESULT.
- **Engine** — RELEASE_RESULT blocked until ACK recorded for critical results; downtime_active → auto NOTIFY_CRITICAL_RESULT on generate, phone/bleep path.
- **query(expr)** — `result_criticality('...')`, `comm_record_exists(result_id='...')`, `notification_mode_required('...')`.
- **Tests** — `tests/test_critical.py`; GS-016, GS-017, GS-018 pass.

### 2.10 Catalogue and stability (START_RUN gating)

- **`policy/catalogue/test_catalogue.seed.v0.1.json`**, **`policy/schemas/test_catalogue.schema.v0.1.json`** — Catalogue seed and schema.
- **`policy/stability/stability_policy.v0.1.yaml`** — Panel-level windows (biochem ambient pre-spin, coag, etc.).
- **`src/labtrust_gym/engine/catalogue_runtime.py`** — Panel lookup by specimen.panel_id, check_stability(), check_temp_out_of_band(); default_stability_limits.
- **Engine** — START_RUN: stability and temp checks; TIME_EXPIRED / TEMP_OUT_OF_BAND BLOCKED unless OVERRIDE_RISK_ACCEPTANCE; START_RUN_OVERRIDE with dual-approval token; CENTRIFUGE_END (separated_ts_s), ALIQUOT_CREATE (aliquot→specimen mapping).
- **Tests** — `tests/test_stability.py`, `tests/test_catalogue.py`; GS-001, GS-006, GS-007 pass.

### 2.11 Co-location (device–agent zone)

- **Device–zone mapping** — From `policy/zones/zone_layout_policy.v0.1.yaml` `device_placement` (and default in zones.py).
- **Engine** — START_RUN and START_RUN_OVERRIDE: if agent zone ≠ device zone ⇒ BLOCKED RC_DEVICE_NOT_COLOCATED, INV-ZONE-002:VIOLATION.
- **Tests** — `tests/test_zones.py` (build_device_zone_map, GS-019, unit colocation test); GS-019 passes.

### 2.12 Queueing (QUEUE_RUN, queue_head, START_RUN consume)

- **Contract (frozen):** **`docs/queue_contract.v0.1.md`** — Device queue item fields, priority ordering rule (STAT/URGENT/ROUTINE), QUEUE_RUN and START_RUN interaction, meaning of `queue_head()`. Do not weaken; queue semantics are a core knob for fairness vs. latency vs. safety.
- **`src/labtrust_gym/engine/queueing.py`** — DeviceQueueItem, DeviceQueue, QueueStore; ordering: priority_rank → enqueued_ts_s → tie_break; enqueue, queue_head(device_id), consume_head(device_id).
- **Engine** — QUEUE_RUN: device_id + work_id (or specimen_id/accession_ids/aliquot_ids); co-location; emit QUEUE_RUN. START_RUN: no explicit work ⇒ consume queue head (else RC_QUEUE_EMPTY); explicit work ⇒ strict work_id == queue_head then consume. Reason codes: RC_DEVICE_UNKNOWN, RC_QUEUE_BAD_PAYLOAD, RC_QUEUE_DUPLICATE_WORK_ID, RC_QUEUE_EMPTY, RC_QUEUE_HEAD_MISMATCH.
- **query(expr)** — `queue_head(DEVICE_ID)` → work_id at front or None.
- **Tests** — `tests/test_queueing.py`; GS-002 passes; full golden suite green with `LABTRUST_RUN_GOLDEN=1`.

---

## 3. Golden scenarios (22 total)

| Scenario | Title / focus | Passes with engine? |
|----------|----------------|----------------------|
| GS-001 | Full pipeline: accession → accept → move → centrifuge → aliquot → queue → start_run → QC → result → release | ✅ |
| GS-002 | STAT insertion; queue_head(DEV_CHEM_A_01) == 'S2' | ✅ (queue contract v0.1 frozen; see docs/queue_contract.v0.1.md) |
| GS-003 | Citrate underfill → HOLD, INV-COAG-FILL-001 | ✅ |
| GS-004 | ID mismatch → REJECT, ID_MISMATCH | ✅ |
| GS-005 | Leaking → REJECT, INT_LEAKING | ✅ |
| GS-006 | Stability expired → BLOCKED; dual approval mint → START_RUN_OVERRIDE | ✅ |
| GS-007 | Temp out-of-band → BLOCKED TEMP_OUT_OF_BAND | ✅ |
| GS-008 | Restricted door without token → BLOCKED | ✅ |
| GS-009 | Door open too long → ALARM, zone frozen | ✅ |
| GS-010 | Dual approval: same approver twice → BLOCKED INV-TOK-001 | ✅ |
| GS-011 | Expired token → BLOCKED | ✅ |
| GS-012 | Token replay (consumed) → BLOCKED | ✅ |
| GS-013 | Revoked token → BLOCKED | ✅ |
| GS-014 | QC fail → RELEASE_RESULT BLOCKED until rerun | ✅ |
| GS-015 | QC drift override, result_flags contains QC_DRIFT_DISCLAIMER_REQUIRED | ✅ |
| GS-016 | Critical: no release until NOTIFY+ACK; INV-CRIT-004 PASS | ✅ |
| GS-017 | ACK without read-back → INV-CRIT-004:VIOLATION, comm_record_exists | ✅ |
| GS-018 | Downtime → NOTIFY_CRITICAL_RESULT, notification_mode_required | ✅ |
| GS-019 | Agent not in device zone → BLOCKED RC_DEVICE_NOT_COLOCATED | ✅ |
| GS-020 | Illegal move (not on graph) → BLOCKED | ✅ |
| GS-021 | HOLD_SPECIMEN without reason_code → BLOCKED | ✅ |
| GS-022 | Hash chain break → forensic freeze, then all BLOCKED | ✅ |

**Full golden suite:** With `LABTRUST_RUN_GOLDEN=1`, the **full suite passes** (22/22). Queue semantics are frozen in **docs/queue_contract.v0.1.md** (v0.1).

---

## 4. What is not implemented (or partial)

### 4.1 Queueing (done; contract frozen)

- **QUEUE_RUN** — Implemented; per-device queue, STAT/URGENT/ROUTINE ordering, co-location, work_id from specimen/accession/aliquot.
- **query(expr): queue_head(device_id)** — Implemented; returns work_id at front or None.
- **START_RUN** — Consumes queue head when no explicit work; strict work_id == queue_head when explicit work.
- **Contract:** **`docs/queue_contract.v0.1.md`** — Frozen; do not weaken (fairness vs. latency vs. safety knob for later work).

### 4.2 Additional engine modules (from spec)

- **state.py / event.py** — No dedicated state/event dataclasses; state is dict-based in core_env and sub-stores.
- **clock.py** — Time advanced implicitly via event `t_s`; no separate clock module.
- **rng.py** — No single RNG wrapper module; determinism via scenario seed and no ambient randomness in current logic.
- **devices.py** — No equipment simulation (timing, batch, failure model); device_placement and QC state only.
- **queueing.py** — Not implemented.
- **errors.py** — Reason codes and BLOCKED responses exist; no dedicated error type module.

### 4.3 Policy schemas

- Only runner output contract and test catalogue have JSON schemas under `policy/schemas/`.
- Tokens, invariants, reason codes, zones, critical results, equipment: no JSON Schema validation in loader/validate (YAML structural checks only where used).

### 4.4 Examples and baselines

- **examples/minimal_random_policy_agent.py** — Present (minimal).
- **scripted_ops_agent.py**, **scripted_runner_agent.py** — Not implemented.
- No MARL or LLM baselines; no benchmark task definitions with formal state distribution, reward functions, or published results.

### 4.5 API and packaging

- **PettingZoo AEC or parallel API** — Not implemented; the environment is used via `LabTrustEnvAdapter` (reset, step, query) for the golden runner.
- **pip-installable** — Yes (`pyproject.toml`, `pip install -e ".[dev]"`); not published to PyPI.

### 4.6 Documentation

- **API reference (autogenerated from docstrings)** — Not set up (e.g. Sphinx/MkDocs).
- **Example notebooks (Jupyter)** — None.
- **docs/** — Short architecture, policy_pack, threat_model, invariants; no detailed “current state” doc except this STATUS.

---

## 5. What remains (prioritized)

1. **Queueing and GS-002** — Done. QUEUE_RUN, queue_head, START_RUN consume; full suite green; contract frozen in docs/queue_contract.v0.1.md.

2. **Full golden suite green**  
   Run full suite with `LABTRUST_RUN_GOLDEN=1` (now green); keep queue contract v0.1 unchanged.

3. **Standard env API**  
   Add a PettingZoo AEC or parallel wrapper so the lab is usable as a standard multi-agent env (observations, actions, rewards, infos).

4. **Benchmark tasks and baselines**  
   Define at least 3 benchmark tasks (state distribution, agents, goals, constraints, reward functions); implement scripted and MARL baselines; document empirical safety/throughput trade-offs.

5. **Docs and examples**  
   API reference from docstrings; Jupyter notebooks for tasks and baselines; expand docs/ (architecture, policy, threat model).

6. **Optional engine refactor**  
   Extract state/event types (state.py, event.py), RNG wrapper (rng.py), and optional clock/queueing/errors modules for clarity and reuse.

7. **Policy schema coverage**  
   Add JSON schemas for tokens, invariants, reason codes, zones, critical, equipment and wire them into `validate-policy` and loader where appropriate.

---

## 6. How to run and validate

```bash
# Install
pip install -e ".[dev]"

# Policy validation (all required policy files and structure)
labtrust validate-policy

# Unit and integration tests (no golden engine)
pytest -q

# Golden suite (requires engine; 21/22 scenarios pass; GS-002 fails on queue_head)
LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -v

# Zone + colocation tests (includes GS-008, GS-009, GS-019, GS-020)
LABTRUST_RUN_GOLDEN=1 pytest tests/test_zones.py -v
```

---

## 7. Summary table

| Category | Implemented | Not implemented / partial |
|----------|-------------|----------------------------|
| Policy load/validate | ✅ loader, validate, CLI, schemas (runner + catalogue) | ❌ Schemas for tokens, invariants, zones, reason_codes, critical, equipment |
| Golden runner | ✅ Adapter, runner, emits strict, contract validation | — |
| Audit / hashchain | ✅ Canonical serialization, chain, fault inject, freeze | — |
| Tokens | ✅ Lifecycle, dual approval, replay protection | — |
| Zones / doors | ✅ Graph, doors, device_placement, colocation | — |
| Specimens | ✅ Acceptance, hold/reject, reason codes | — |
| QC | ✅ Device state, result gating, drift override | — |
| Critical | ✅ Classify, notify/ack, downtime path | — |
| Catalogue / stability | ✅ Panel, stability, temp, START_RUN gating | — |
| Co-location | ✅ START_RUN / START_RUN_OVERRIDE device zone check | — |
| Queueing | ✅ queueing.py, QUEUE_RUN, queue_head, START_RUN consume; docs/queue_contract.v0.1.md | — |
| Engine structure | ✅ core_env + domain modules (incl. queueing.py) | ❌ state.py, event.py, clock, rng, devices, errors as separate modules |
| Env API | ✅ Adapter (reset, step, query) | ❌ PettingZoo AEC/parallel |
| Examples | ✅ minimal_random_policy_agent | ❌ scripted_ops, scripted_runner, MARL, LLM |
| Docs | ✅ README, CONTRIBUTING, short docs/ | ❌ API ref, notebooks, full “current state” (this file fills that gap) |

This STATUS is the single place that reports the current state of the repo, what was implemented, what was not, and what remains.
