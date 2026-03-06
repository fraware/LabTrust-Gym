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

- **Loader**: `src/labtrust_gym/policy/loader.py` loads the enforcement map (and partner overlay); schema validation is via `labtrust validate-policy`.
- **Engine**: `src/labtrust_gym/engine/enforcement.py` — `EnforcementEngine` loads the map, matches violations, applies escalation, and returns a list of enforcement items. Violation counts are stored per (agent_id, rule_id); call `reset_counts()` on env reset.
- **Integration**: `core_env._finalize_step()` calls the enforcement engine when `enforcement_enabled` is true and merges **enforcements** into the step result; each enforcement is appended to the audit log.

## Evidence bundle

Runs can be exported into a stable **EvidenceBundle.v0.1** directory for audit and reproducibility. Each released (or held/rejected) specimen or result gets a **Receipt.v0.1** JSON file; the bundle also includes a subset of the episode log, invariant and enforcement traces, hashchain proof, and a manifest.

### Schemas

- **policy/schemas/receipt.v0.1.schema.json** — Per-specimen/result receipt: identifiers, timestamps, decision (RELEASED | HELD | REJECTED | BLOCKED), reason_codes, tokens, critical comm records, invariant/enforcement summary, hashchain.
- **policy/schemas/evidence_bundle_manifest.v0.1.schema.json** — Manifest: list of files with SHA-256, policy_fingerprint, partner_id, optional signature (Ed25519; see below).

### CLI

```bash
labtrust export-receipts --run <episode_log.jsonl> --out <dir>
```

- **--run**: Path to episode log (JSONL), e.g. `runs/repro_minimal_xxx/taska/logs/cond_0/episodes.jsonl`.
- **--out**: Output directory; creates `EvidenceBundle.v0.1/` under it.

Output is deterministic (same log ⇒ identical bundle). Receipts validate against the receipt schema; the manifest validates against the evidence_bundle_manifest schema.

### Bundle contents

- **receipt_&lt;type&gt;_&lt;id&gt;.v0.1.json** — One file per specimen/result (stable filenames).
- **episode_log_subset.jsonl** — Relevant events (full log for single-episode).
- **invariant_eval_trace.jsonl** — Per-step invariant evaluations (violations).
- **enforcement_actions.jsonl** — Per-step enforcement actions (throttle, kill_switch, freeze_zone, forensic_freeze).
- **hashchain_proof.json** — head_hash, last_event_hash, length, break_status.
- **manifest.json** — Files with sha256, policy_fingerprint, partner_id, optional Ed25519 signature.

### Evidence bundle signing and verification

Signing is **key-custody agnostic**: the core export does not read keys from disk. The runner supplies a `get_private_key(key_id)` callback and a key registry (e.g. from `policy/keys/key_registry.v0.1.yaml` plus overlays). When `sign_bundle=True` and these are provided, the manifest and each receipt are signed with Ed25519. Signature format: `{"algorithm": "ed25519", "public_key_b64": ..., "signature_b64": ..., "key_id": ...}`. Verification uses the same key registry: `verify_receipt(receipt, key_registry)` and `verify_manifest_signature(manifest, key_registry)`. The `labtrust verify-bundle` command runs these checks when the key registry is present under the policy root; tampering with signed content causes verification to fail.

## Tests

- **tests/test_enforcement.py**: Load map, throttle on violation, escalation on repeated violations, deterministic ordering, core_env with enforcement disabled returns empty enforcements.
- **tests/test_export_receipts.py**: Deterministic export, receipt and manifest schema validation, coverage for release, hold, reject, blocked, and forensic-freeze cases.
