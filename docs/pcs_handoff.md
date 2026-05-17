# PCS cross-repo handoff contract (v0.1)

LabTrust-Gym exports a **handoff bundle** for CertifyEdge and Provability Fabric without adapting to PF legacy singular `runtime_receipt` fields. Consumers must use pcs-core `ScienceClaimBundle.v0` shape: `runtime_receipts[]` and `certificates[]`.

## Command

```bash
labtrust export-pcs-handoff --out handoff/
# Fixture-stable layout (CI / goldens):
PCS_DETERMINISTIC=1 labtrust export-pcs-handoff --out handoff/
```

## Directory layout

```
handoff/
  manifest.json
  certifyedge/
    valid_trace.json
    invalid_missing_qc_trace.json
    invalid_unauthorized_trace.json
  provability_fabric/
    trace.json
    runtime_receipt.json          # RuntimeReceipt.v0 file (singular filename OK)
    science_claim_bundle.pending.json
```

## manifest.json

| Field | Meaning |
|-------|---------|
| `handoff_version` | `v0.1` |
| `deterministic` | `true` when `PCS_DETERMINISTIC=1` was used |
| `scenarios` | Map demo name → `{ "trace": "certifyedge/<file>", "run_dir": "..." }` |
| `provability_fabric` | Paths under `provability_fabric/`, `claim_id`, `limitations_doc` |
| `trace_hash_rule` | Doc anchor for trace/receipt alignment |

## Consumer mapping

| Repo | Inputs from handoff | Output expected |
|------|---------------------|-----------------|
| **CertifyEdge** | `certifyedge/*.json` traces | `TraceCertificate.v0` (`trace_certificate.json`) |
| **Provability Fabric** | `science_claim_bundle.pending.json` + certificate | `SignedScienceClaimBundle.v0` (verify/sign) |
| **Scientific Memory** | PF signed bundle | Import/render (out of LabTrust CI scope) |

## Canonical bundle rules

- Pending bundle: `runtime_receipts` (array, min 1), `certificates` (array, may be empty).
- Do **not** require or emit top-level `runtime_receipt: {}` (PF local legacy).
- `schema_version` is always `"v0"` for pcs-core artifacts (not artifact-name versions like `RuntimeReceipt.v0` in the field).

## Validation

```bash
pcs validate handoff/provability_fabric/runtime_receipt.json
pcs validate handoff/provability_fabric/science_claim_bundle.pending.json
labtrust validate-pcs --artifact handoff/provability_fabric/science_claim_bundle.pending.json
```

See also [pcs_export.md](pcs_export.md), [pcs_trace_model.md](pcs_trace_model.md), and [examples/pcs_qc_release/RUNBOOK.md](../examples/pcs_qc_release/RUNBOOK.md).
