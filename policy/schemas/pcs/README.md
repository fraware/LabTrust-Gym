# PCS JSON schemas (LabTrust profile)

LabTrust-Gym validates exported PCS artifacts with **pcs-core** (`RuntimeReceipt.v0`, `ScienceClaimBundle.v0`, `TraceCertificate.v0`, etc.). Files in this directory are **reference copies** for documentation and policy validation; they are not the sole source of truth.

## Authoritative validation

- Install [pcs-core](https://github.com/SentinelOps-CI/pcs-core) and run `pcs validate <artifact.json>` or `labtrust validate-pcs --artifact <path>`.
- CI (`.github/workflows/pcs.yml`) patches `runtime_receipt.v0.schema.json` into the pcs-core checkout to apply the LabTrust **RuntimeReceipt profile** (`run_outcome`, `final_reason_code`, `released`, `local_dev`).

## LabTrust-specific artifacts

| Artifact | pcs-core type | Notes |
|----------|---------------|--------|
| Hash-chained workflow trace | (LabTrust profile) | `schema_version: v0`, `trace_hash` as `sha256:…`; see `docs/pcs_trace_model.md` |
| `runtime_receipt.json` | `RuntimeReceipt.v0` | Single receipt file; bundled as `runtime_receipts[]` in ScienceClaimBundle |
| `science_claim_bundle.*.json` | `ScienceClaimBundle.v0` | Must use `runtime_receipts` and `certificates` arrays (not PF legacy `runtime_receipt` singular) |

## Stale local schemas

`trace.v0.schema.json` and `science_claim_bundle.v0.schema.json` may lag pcs-core; prefer pcs-core `schemas/` for contract tests. Do not use them to block exports that already pass `pcs_core.validate.validate_artifact`.
