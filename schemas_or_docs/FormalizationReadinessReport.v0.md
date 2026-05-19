# FormalizationReadinessReport.v0

LabTrust emits this report during `regenerate-release-protocol`. It records whether
release artifacts are complete enough for **pcs-core** to extract Lean proof
obligations. LabTrust does **not** run Lean.

## Scope

- `formalization_scope` is always `trust_envelope_only`.
- Hospital/lab workflow semantics are **not** claimed to be formalized in Lean.

## Related artifacts

| File | Role |
|------|------|
| `proof_obligation_hints.json` | Artifact paths for obligation extraction |
| `proof_obligation_identifiers.json` | Stable IDs (receipt, trace/cert hashes, commits) |
| `workflow_profile.v0.json` | `formalization` extension block (LabTrust-validated; stripped for pcs-core schema) |

## Schema

`policy/schemas/pcs/FormalizationReadinessReport.v0.schema.json`

## CI

```bash
python examples/pcs_qc_release/scripts/ci_validate_formalization.py
```
