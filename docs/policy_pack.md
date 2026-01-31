# Policy pack

Policy is versioned under `policy/`. For the canonical list of **frozen contracts and schema versions** (anti-regression backbone), see [Frozen contracts](frozen_contracts.md).

- **schemas/**: JSON schemas for runner output contract, test catalogue, invariant registry v1.0, and all policy YAML/JSON (emits vocab, zones, reason codes, token registry, dual approval, critical thresholds, equipment registry, enforcement map, golden scenarios). Validated by `labtrust validate-policy`.
- **emits/**: Canonical emit vocabulary; engines must only emit listed types.
- **invariants/**: Invariant registry v1.0 (token, zone, critical-result, stability, etc.); machine-readable logic templates; schema in `schemas/invariant_registry.v1.0.schema.json`.
- **tokens/**: Token registry, dual-approval policy, token enforcement map.
- **reason_codes/**: Canonical reason codes for HOLD/REJECT/block.
- **zones/**: Zone layout, doors, graph edges, device placement.
- **catalogue/**: Test catalogue seed (panels, tests, shared vocab).
- **stability/**: Panel stability and temperature rules.
- **equipment/**: Device types and instances.
- **critical/**: Critical result thresholds.
- **enforcement/**: Enforcement map (match invariant/severity/scope → throttle, kill_switch, freeze_zone, forensic_freeze; escalation tiers).
- **studies/**: Study spec example and schema (ablations, task, episodes, seed_base).
- **llm/**: LLM action schema (action_type, action_info) for baselines.
- **golden/**: Golden scenario suite YAML.

All policy files are validated in CI. Unknown emits in step results fail the golden suite.
