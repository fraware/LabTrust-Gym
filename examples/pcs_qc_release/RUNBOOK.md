# PCS QC-release end-to-end runbook

## 1. Overview

This runbook walks through the LabTrust-Gym PCS v0.1 QC-release demonstration. LabTrust-Gym simulates a minimal lab workflow (accession, QC, analysis, release), records a hash-chained trace, and exports PCS artifacts (`RuntimeReceipt.v0`, `EvidenceBundle.v0`, `ScienceClaimBundle.v0`). Downstream repos certify the trace, verify and sign the bundle, and import into Scientific Memory.

**Main claim (protocol safety):** A sample may be released only after accession, QC completion, analysis, authorization by a release-capable actor, and satisfaction of the required temporal protocol constraints.

This is a **research/simulation** artifact, not a clinical deployment.

## 2. Repositories required

| Repository | Role |
|------------|------|
| [LabTrust-Gym](https://github.com/fraware/LabTrust-Gym) | Workflow simulation, trace, PCS export |
| [pcs-core](https://github.com/SentinelOps-CI/pcs-core) | Schema validation, canonical hashing |
| [CertifyEdge](https://github.com/fraware/CertifyEdge) | `TraceCertificate.v0` |
| [provability-fabric](https://github.com/SentinelOps-CI/provability-fabric) | Verify and sign bundles |
| [scientific-memory](https://github.com/fraware/scientific-memory) | Import and render signed claims |

## 3. Toolchain requirements

- Python 3.11+
- `pip install -e ".[dev]"` in LabTrust-Gym
- Optional: `pip install -e /path/to/pcs-core/python` for `pcs validate`
- Git (for `source_commit` in artifacts)
- CertifyEdge, Provability Fabric, and Scientific Memory per their runbooks for steps 4–10

## 4. Step 1: run valid LabTrust workflow

```bash
labtrust run-demo qc-release
# default output: runs/qc-release/
```

Verify `runs/qc-release/run_meta.json` has `"status": "completed"`, `"released": true`, `"final_reason_code": "ok"`.

## 5. Step 2: run invalid LabTrust workflows

```bash
labtrust run-demo qc-release-invalid-missing-qc
labtrust run-demo qc-release-invalid-unauthorized
```

Expected: `final_reason_code` is `missing_qc` and `unauthorized_release` respectively; `released` is false.

## 6. Step 3: export trace and runtime receipt

```bash
labtrust export-trace --run runs/qc-release --out trace.json
labtrust export-runtime-receipt --run runs/qc-release --out runtime_receipt.json
labtrust export-pcs --run runs/qc-release --out science_claim_bundle.pending.json
```

Validate with pcs-core when installed:

```bash
pcs validate runtime_receipt.json
pcs validate science_claim_bundle.pending.json
```

`runtime_receipt.json` field `trace_hash` must equal `trace.json` top-level `trace_hash`.

## 7. Step 4: certify trace with CertifyEdge

```bash
certifyedge emit-pcs-certificate \
  --spec templates/hospital_lab/qc_release.stl \
  --trace trace.json \
  --out trace_certificate.json
```

CertifyEdge emits `TraceCertificate.v0` with `trace_hash` aligned to the runtime receipt.

## 8. Step 5: attach TraceCertificate to ScienceClaimBundle

```bash
labtrust attach-certificate \
  --bundle science_claim_bundle.pending.json \
  --certificate trace_certificate.json \
  --out science_claim_bundle.certified.json
```

After attach: `certificates` is non-empty; `claim_artifact.certificate_refs` references the certificate id; `claim_artifact.status` is `CertificateChecked`.

## 9. Step 6: verify and sign with Provability Fabric

```bash
pf verify science-claim science_claim_bundle.certified.json
pf sign science-claim science_claim_bundle.certified.json \
  --out signed_science_claim_bundle.json
```

## 10. Step 7: import into Scientific Memory

```bash
just pcs-import-bundle BUNDLE=signed_science_claim_bundle.json
just pcs-render-claim CLAIM_ID=<claim_id>
```

Use `claim_id` from the signed bundle (`claim-pcs-qc-release-v0.1` in the demo).

## 11. Expected output files

| Path | Artifact |
|------|----------|
| `trace.json` | Hash-chained workflow trace |
| `runtime_receipt.json` | `RuntimeReceipt.v0` |
| `runs/qc-release/pcs/evidence_bundle.json` | `EvidenceBundle.v0` |
| `science_claim_bundle.pending.json` | Pending `ScienceClaimBundle.v0` |
| `science_claim_bundle.certified.json` | Certified bundle |
| `trace_certificate.json` | `TraceCertificate.v0` |
| `signed_science_claim_bundle.json` | PF-signed bundle |

Golden references: `examples/pcs_qc_release/expected/`.

## 12. Troubleshooting

- **`pcs validate` fails:** Install pcs-core; ensure digests use `sha256:` prefix and `schema_version` is `v0`.
- **trace_hash mismatch:** Re-export trace and receipt from the same `run_dir`; do not edit events after export.
- **attach-certificate fails:** Certificate `trace_hash` must match `runtime_receipt.trace_hash`.
- **Invalid demos pass release:** Check `policy/pcs/roles.yaml`; only `release_manager` is `release_capable`.

## 13. Limitations

- Simulation only; no real LIS/hospital integration.
- No clinical safety or regulatory claims.
- Trace model is LabTrust-specific; PCS bundles follow pcs-core schemas.
- Certification and signing require external repos and are not bundled in LabTrust-Gym CI by default.

See also [docs/pcs_limitations.md](../../docs/pcs_limitations.md).
