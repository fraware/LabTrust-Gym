# Policy pack

Policy is versioned under `policy/`:

- **schemas/**: JSON schemas for runner output contract, test catalogue, and all policy YAML/JSON (emits vocab, zones, reason codes, token registry, dual approval, critical thresholds, equipment registry, golden scenarios). Validated by `labtrust validate-policy`.
- **emits/**: Canonical emit vocabulary; engines must only emit listed types.
- **invariants/**: Token, zone, and critical-result invariants.
- **tokens/**: Token registry, dual-approval policy, enforcement map.
- **reason_codes/**: Canonical reason codes for HOLD/REJECT/block.
- **zones/**: Zone layout, doors, graph edges, device placement.
- **catalogue/**: Test catalogue seed (panels, tests, shared vocab).
- **stability/**: Panel stability and temperature rules.
- **equipment/**: Device types and instances.
- **golden/**: Golden scenario suite YAML.

All policy files are validated in CI. Unknown emits in step results fail the golden suite.
