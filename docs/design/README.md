# Design and legacy reference files

This directory holds **reference and legacy** YAML/JSON from earlier design or tooling. They are **not** loaded by the runtime; the single source of truth for policy is `policy/` at the repo root.

| File | Description |
|------|--------------|
| `aliases_v0.1.yaml` | Alias / naming reference |
| `compiler_contract.yaml` | Compiler contract spec |
| `invariants_generated.v0.1.yaml` | Generated invariants (reference) |
| `override_matrix_v0.1.yaml` | Override matrix reference |
| `policy_pack_hsl_blood_sciences_v0.1.yaml` | HSL blood sciences policy pack (reference) |
| `reason_code_compiler_rules.v0.1.yaml` | Reason code compiler rules |
| `runtime_enforcement_api.yaml` | Runtime enforcement API spec |

Canonical policy lives under **`policy/`**: schemas, emits, invariants, tokens, reason_codes, zones, catalogue, stability, equipment, critical, golden.
