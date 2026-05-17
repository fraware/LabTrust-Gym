# Cross-repo PCS v0.1 release candidate fixtures (`release/`)

These artifacts are the **release candidate** set for CertifyEdge, Provability Fabric, and Scientific Memory handoff. They must use a **real** `TraceCertificate.v0` from the CertifyEdge CLI—not the LabTrust mock in `expected/trace_certificate.mock.v0.json`.

## Required files

| File | Source |
|------|--------|
| `trace.json` | `labtrust export-trace` |
| `runtime_receipt.json` | `labtrust export-runtime-receipt` |
| `science_claim_bundle.pending.json` | `labtrust export-pcs` |
| `trace_certificate.json` | `certifyedge emit-pcs-certificate` |
| `science_claim_bundle.certified.json` | `labtrust attach-certificate` |
| `manifest.json` | Written by generator (records CertifyEdge path and generation time) |

## Generate

From LabTrust-Gym repo root, with sibling checkouts (or set env vars):

```bash
export PCS_DETERMINISTIC=1
# optional overrides:
# export CERTIFYEDGE_BIN=certifyedge
# export CERTIFYEDGE_ROOT=../CertifyEdge
# export CERTIFYEDGE_SPEC=$CERTIFYEDGE_ROOT/templates/hospital_lab/qc_release.stl

bash examples/pcs_qc_release/scripts/generate_release_candidate.sh
```

Windows:

```powershell
$env:PCS_DETERMINISTIC = "1"
& examples/pcs_qc_release/scripts/generate_release_candidate.ps1
```

After generation, commit `release/` when the PCS schema or QC-release contract changes.

## Validation

```bash
pytest tests/pcs/test_release_fixtures.py -q
```

Tests skip when `release/trace_certificate.json` is absent (typical in LabTrust-only CI). Run locally after generating with CertifyEdge installed.
