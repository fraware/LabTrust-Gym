# Policy pack

Policy is versioned under `policy/`. For the canonical list of **frozen contracts and schema versions** (anti-regression backbone), see [Frozen contracts](../contracts/frozen_contracts.md).

- **schemas/**: JSON schemas for runner output contract, test catalogue, invariant registry v1.0, and all policy YAML/JSON (emits vocab, zones, reason codes, token registry, dual approval, critical thresholds, equipment registry, enforcement map, golden scenarios, **receipt v0.1**, **evidence_bundle_manifest v0.1**, **fhir_bundle_export v0.1**, **sites_policy v0.1**, **key_registry v0.1**, **rbac_policy v0.1**, escalation_ladder v0.2, partners_index). Validated by `labtrust validate-policy`. After validate-policy, review policy for logical consistency and appropriateness of controls; validation is necessary but not sufficient.
- **emits/**: Canonical emit vocabulary; engines must only emit listed types (incl. transport: DISPATCH_TRANSPORT, TRANSPORT_TICK, RECEIVE_TRANSPORT, CHAIN_OF_CUSTODY_SIGN).
- **invariants/**: Invariant registry v1.0 (token, zone, critical-result, stability, transport INV-COC-001, INV-TRANSPORT-001, etc.); machine-readable logic templates; schema in `schemas/invariant_registry.v1.0.schema.json`.
- **tokens/**: Token registry, dual-approval policy, token enforcement map.
- **reason_codes/**: Canonical reason codes for HOLD/REJECT/block (incl. TRANSPORT_ROUTE_FORBIDDEN, TRANSPORT_TEMP_EXCURSION, TRANSPORT_CHAIN_OF_CUSTODY_BROKEN).
- **zones/**: Zone layout, doors, graph edges, device placement.
- **keys/**: **Key registry v0.1** — Ed25519 public keys for signed actions. **Lifecycle**: each key has optional `status` (ACTIVE, REVOKED, EXPIRED), optional `not_before_ts_s` / `not_after_ts_s` (validity window). Signature verification checks: key exists; status ACTIVE (default if omitted); `now_ts` within [not_before_ts_s, not_after_ts_s]; key bound to event `agent_id` and `role_id` (INV-SIG-002). Reason codes: SIG_KEY_REVOKED, SIG_KEY_EXPIRED, SIG_KEY_NOT_YET_VALID. No breaking changes: all lifecycle fields optional; missing status defaults to ACTIVE; missing time bounds mean no window restriction.
- **rbac/**: **RBAC policy v0.1** — roles (allowed_actions, allowed_zones, allowed_devices), agents (agent_id → role_id), optional action_constraints. Engine gates actions before state mutation; token cannot bypass RBAC. Reason codes: RBAC_ACTION_DENY, RBAC_ZONE_DENY, RBAC_DEVICE_DENY.
- **sites/**: **Sites policy v0.1** — multi-site topology (SITE_HUB, SITE_ACUTE), site graph, routes (transport_time_mean_s, temp_drift). Used by engine/transport.py.
- **catalogue/**: Test catalogue seed (panels, tests, shared vocab).
- **stability/**: Panel stability and temperature rules.
- **equipment/**: Device types and instances.
- **critical/**: Critical result thresholds; **escalation_ladder v0.2** (tiers, max_ack_wait_s, required_fields, requires_readback). Default file `critical_thresholds.v0.1.yaml` provides reference defaults (RCPath 2017 style); see [Production calibration (critical thresholds)](#production-calibration-critical-thresholds) for site use.

## Production calibration (critical thresholds)

The engine loads critical thresholds from `policy/critical/critical_thresholds.v0.1.yaml` (or the   merged policy when using a partner). The shipped file contains **reference defaults** (RCPath 2017 style); they are **not clinically validated**. For production:

- **Partner overlay:** Put a site-calibrated `critical_thresholds.v0.1.yaml` (or the subset you override) under `policy/partners/<partner_id>/critical/` and run with `--partner <partner_id>` or `LABTRUST_PARTNER=<partner_id>`. The loader merges overlay over base.
- **Custom policy root:** Set `LABTRUST_POLICY_DIR` to a directory that contains your own `critical/critical_thresholds.v0.1.yaml`. The engine uses that tree instead of the package/repo policy.

No code change is required; the existing loader and partner merge already support overrides. See [Calibration guide](calibration_guide.md) for what to tune, where in policy, and how to validate.
- **enforcement/**: Enforcement map (match invariant/severity/scope → throttle, kill_switch, freeze_zone, forensic_freeze; escalation tiers).
- **studies/**: Study spec example and schema (ablations, task, episodes, seed_base).
- **llm/**: LLM action schema v0.2 (`llm_action.schema.v0.2.json`: action_type, args, key_id, signature, token_refs, reason_code, rationale), policy summary schema (`policy_summary.schema.v0.1.json`) for baselines.
- **golden/**: Golden scenario suite YAML (incl. GS-CRIT-023, GS-CRIT-024, GS-CRIT-025).
- **partners/**: Partner overlay index (`partners_index.v0.1.yaml`) and per-partner overlay dirs (e.g. `partners/hsl_like/`). Overlays override only specific subtrees (critical thresholds, stability, enforcement map, equipment, escalation_ladder) without code forks. See [Partner overlays](#partner-overlays) below.

All policy files are validated in CI. Unknown emits in step results fail the golden suite.

## Policy resolution at reset

When the engine resets (`core_env.reset()`), each policy value (e.g. RBAC, key registry, zones) is resolved by `engine/policy_resolution.py`: **effective_policy[key]** if present and valid, else **load from policy_root** (file on disk), else **default**. Initial state can supply `effective_policy` (e.g. from a partner overlay via `load_effective_policy`) and `policy_root`. This keeps scenario overrides and file-based policy in one place. See [System overview: Policy at runtime](../architecture/system_overview.md#policy-at-runtime).

## Partner overlays

Partner profiles can override selected policy subtrees via **partner overlays** under `policy/partners/<partner_id>/`. Merge rules are explicit and per-type:

- **Maps (reason_codes, emits):** Overlay may add; may not delete base entries.
- **Thresholds / stability / equipment:** Overlay may replace entries by key; required keys kept.
- **Enforcement map:** Overlay may add or override rules by `rule_id`; core severities remain covered.

Effective policy is **base + overlay** (deterministic merge). A **policy_fingerprint** (SHA-256 of canonical merged policy) is recorded in episode logs and study/benchmark outputs.

- **CLI:** `labtrust validate-policy --partner <partner_id>`, `labtrust run-benchmark --partner <partner_id>`, `labtrust run-study --partner <partner_id>`. Environment variable `LABTRUST_PARTNER` also sets the partner.
- **Index:** `policy/partners/partners_index.v0.1.yaml` lists partner ids and overlay paths. Example overlay: `policy/partners/hsl_like/` (critical, stability, enforcement overrides).
