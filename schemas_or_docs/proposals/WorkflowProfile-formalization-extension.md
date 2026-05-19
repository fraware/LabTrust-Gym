# Proposal: WorkflowProfile `formalization` block (pcs-core)

## Summary

Add an optional `formalization` object to `WorkflowProfile.v0` so benches declare
which Lean obligations apply and that formalization is limited to the PCS trust
envelope.

## Suggested shape

```json
{
  "formalization": {
    "trust_kernel": "labtrust.pcs.trust_envelope.v0",
    "required_obligations": [
      "CertificateMatchesRuntime",
      "CertificateStatusAllowed",
      "VerificationAdmitsBundle",
      "SignedBundleAdmissible"
    ],
    "formalization_scope": "trust_envelope_only"
  }
}
```

## LabTrust interim

- Validated locally via `policy/schemas/pcs/WorkflowProfile.formalization.extension.schema.json`
- Stripped before `pcs_core.validate` until pcs-core adopts the field

## Reference

- `examples/pcs_qc_release/workflow_profile.v0.json`
- `src/labtrust_gym/pcs/formalization.py`
