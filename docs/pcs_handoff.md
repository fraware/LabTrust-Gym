# PCS cross-repo handoff contract (v0.1)

LabTrust-Gym exports a **handoff bundle** for CertifyEdge and Provability Fabric using the pcs-core `ScienceClaimBundle.v0` shape with `runtime_receipts[]` and `certificates[]`. Top-level layout uses the array form expected by current pcs-core consumers.

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
| `trace_hash_rule` | Doc anchor for trace and receipt alignment |

## Consumer mapping

| Repo | Inputs from handoff | Output expected |
|------|---------------------|-----------------|
| **CertifyEdge** | `certifyedge/*.json` traces | `TraceCertificate.v0` (`trace_certificate.json`) |
| **Provability Fabric** | `science_claim_bundle.pending.json` + certificate | `SignedScienceClaimBundle.v0` (verify and sign) |
| **Scientific Memory** | PF signed bundle | Import and render (outside LabTrust CI scope) |

## Canonical bundle rules

- Pending bundles include `runtime_receipts` (array, minimum length 1) and `certificates` (array, may be empty).
- Use `runtime_receipts[]` (array) at the bundle top level; the legacy singular `runtime_receipt` field is unused in v0 handoffs.
- Set `schema_version` to `"v0"` for pcs-core artifacts (distinct from artifact type names such as `RuntimeReceipt.v0` in filenames).

## Validation

```bash
pcs validate handoff/provability_fabric/runtime_receipt.json
pcs validate handoff/provability_fabric/science_claim_bundle.pending.json
labtrust validate-pcs --artifact handoff/provability_fabric/science_claim_bundle.pending.json
```

See also [pcs_export.md](pcs_export.md), [pcs_trace_model.md](pcs_trace_model.md), and the [PCS operator runbook](examples/pcs_qc_release-operator.md).
