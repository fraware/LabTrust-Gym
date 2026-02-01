# Frozen contracts

This page is the **canonical list of frozen contracts and schema versions** for LabTrust-Gym. These define correctness and the anti-regression backbone; do not weaken them without an explicit design change and version bump.

| Contract / schema | Version | Location | Purpose |
|------------------|---------|----------|---------|
| **Runner output contract** | v0.1 | `policy/schemas/runner_output_contract.v0.1.schema.json` | Shape of each `step()` return: `status`, `emits`, `violations`, `blocked_reason_code`, `token_consumed`, `hashchain`, optional `state_snapshot`. Golden runner and engine must conform. |
| **Queue contract** | v0.1 | [queue_contract.v0.1.md](queue_contract.v0.1.md) | Device queue semantics: item fields, priority ordering (STAT/URGENT/ROUTINE), `QUEUE_RUN` / `START_RUN` interaction, meaning of `queue_head(device_id)`. Fairness vs. latency vs. safety knob. |
| **Invariant registry schema** | v1.0 | `policy/schemas/invariant_registry.v1.0.schema.json` | Schema for `policy/invariants/invariant_registry.v1.0.yaml`: invariant_id, title, severity, scope, signals, logic_template, exception_hooks, enforcement_hint. |
| **Enforcement map schema** | v0.1 | `policy/schemas/enforcement_map.v0.1.schema.json` | Schema for `policy/enforcement/enforcement_map.v0.1.yaml`: rules matching invariant_id/severity/scope → actions (throttle_agent, kill_switch, freeze_zone, forensic_freeze); escalation tiers. |
| **Study spec schema** | v0.1 | `policy/studies/study_spec.schema.v0.1.json` | Schema for study specs: task, episodes, seed_base, ablations; used by `labtrust run-study` for reproducible experiment definitions. |
| **Receipt schema** | v0.1 | `policy/schemas/receipt.v0.1.schema.json` | Per-specimen/result receipt (identifiers, timestamps, decision, reason_codes, tokens, invariant/enforcement summary, hashchain). Used by export-receipts. |
| **Evidence bundle manifest schema** | v0.1 | `policy/schemas/evidence_bundle_manifest.v0.1.schema.json` | Manifest for EvidenceBundle.v0.1: files (path, sha256), policy_fingerprint, partner_id. |
| **FHIR bundle export schema** | v0.1 | `policy/schemas/fhir_bundle_export.v0.1.schema.json` | Minimal structural contract for FHIR R4 Bundle export (resourceType, type, entry). Not full FHIR validation. |
| **Sites policy schema** | v0.1 | `policy/schemas/sites_policy.v0.1.schema.json` | Schema for `policy/sites/sites_policy.v0.1.yaml`: sites, site_graph, routes (transport_time, temp_drift). Used by engine/transport. |
| **Key registry schema** | v0.1 | `policy/schemas/key_registry.v0.1.schema.json` | Schema for `policy/keys/key_registry.v0.1.yaml`: Ed25519 keys (key_id, public_key, agent_id, role_id); optional status (ACTIVE/REVOKED/EXPIRED), not_before_ts_s, not_after_ts_s. Used by engine/signatures; lifecycle enforced in verification. |
| **RBAC policy schema** | v0.1 | `policy/schemas/rbac_policy.v0.1.schema.json` | Schema for `policy/rbac/rbac_policy.v0.1.yaml`: roles (allowed_actions, allowed_zones, allowed_devices), agents (agent_id → role_id), action_constraints. Used by engine/rbac. |
| **Benchmark results schema** | v0.2 | `policy/schemas/results.v0.2.schema.json` | Normative benchmark results: task, seeds, policy_fingerprint, partner_id, git_sha, agent_baseline_id, episodes with metrics. Used by run-benchmark output and summarize-results. |

## Runner output contract (v0.1)

The engine and any adapter implementing `LabTrustEnvAdapter` must return step results that validate against `policy/schemas/runner_output_contract.v0.1.schema.json`. Key fields:

- `status`: `"ACCEPTED"` or `"BLOCKED"`
- `emits`: list of emit strings (must be in `policy/emits/emits_vocab.v0.1.yaml`)
- `violations`: list of `{ invariant_id, status, reason_code }`
- `blocked_reason_code`: present when `status == "BLOCKED"`; must be in reason code registry
- `token_consumed`: list of token IDs consumed this step
- `hashchain`: `{ head_hash, length, last_event_hash }` (append-only; chain break → forensic freeze)

Validated in CI via `labtrust validate-policy` and by the golden runner against step outputs.

## Queue contract (v0.1)

Behavioral contract for device queues: see [Queue contract v0.1](queue_contract.v0.1.md). Covers `DeviceQueueItem` fields, priority ordering, `QUEUE_RUN` validation, `START_RUN` consuming queue head, and `query('queue_head(device_id)')`. Golden scenario GS-002 and queueing tests depend on it.

## Invariant registry schema (v1.0)

Defines the structure of the machine-readable invariant registry (`policy/invariants/invariant_registry.v1.0.yaml`). Used by `labtrust validate-policy` and by `invariants_runtime` to compile and evaluate invariants post-step.

## Enforcement map schema (v0.1)

Defines the structure of the enforcement map (`policy/enforcement/enforcement_map.v0.1.yaml`). Maps violation conditions to actions (throttle, kill_switch, freeze_zone, forensic_freeze). Validated by `labtrust validate-policy`; consumed by `engine/enforcement.py`.

## Study spec schema (v0.1)

Defines the structure of study specification YAMLs (e.g. `policy/studies/study_spec.example.v0.1.yaml`). Used by `labtrust run-study` to expand ablations and run benchmark conditions. Ensures reproducible experiment definitions.

## Receipt and evidence bundle (v0.1)

Receipt and evidence bundle manifest schemas define the shape of exported receipts (per specimen/result) and the EvidenceBundle.v0.1 manifest (files + sha256, policy_fingerprint). Validated when exporting; see [Enforcement](enforcement.md) (evidence bundle section) and [FHIR R4 export](fhir_export.md).

## FHIR bundle export (v0.1)

Minimal structural contract for FHIR R4 Bundle export (resourceType Bundle, type collection, entry with fullUrl and resource). Not full FHIR profile validation. See [FHIR R4 export](fhir_export.md).

## Sites policy (v0.1)

Schema for `policy/sites/sites_policy.v0.1.yaml`: sites, site_graph, routes (transport_time_mean_s, temp_drift). Used by `labtrust validate-policy` and engine/transport.

---

See also: [Policy pack and schemas](policy_pack.md), [STATUS](STATUS.md) (§1.3 What's frozen).
