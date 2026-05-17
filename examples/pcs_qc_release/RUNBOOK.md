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

**LabTrust-only smoke** (requires `pcs-core` installed, e.g. `pip install -e ../pcs-core/python`):

```bash
bash examples/pcs_qc_release/scripts/labtrust_only_smoke.sh
```

**Deterministic fixture mode** (golden artifacts / CI only; freezes `source_commit`, environment, and digests):

```bash
labtrust run-demo qc-release --deterministic
# or: PCS_DETERMINISTIC=1 labtrust run-demo qc-release
```

Regenerate committed goldens after schema changes:

```bash
python examples/pcs_qc_release/scripts/generate_golden.py
```

ScienceClaimBundle exports use PCS-core canonical shape: top-level `runtime_receipts` (array) and `certificates` (array). LabTrust does not emit PF legacy `runtime_receipt` (singular).

Handoff bundle for CertifyEdge / Provability Fabric: `labtrust export-pcs-handoff --out handoff/` (see [docs/pcs_handoff.md](../../docs/pcs_handoff.md)).

**In-repo CI scope:** `pytest tests/pcs` plus `python examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py` (deterministic export, `pcs validate`, golden snapshot checks). CertifyEdge, Provability Fabric, and Scientific Memory steps are documented for cross-repo integration but are not executed in `.github/workflows/pcs.yml`.

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

Provability Fabric emits a top-level **`SignedScienceClaimBundle.v0`** object in `signed_science_claim_bundle.json` (artifact class name; not the value of `schema_version`).

**Signed bundle contract (pcs-core v0):**

| Field | Rule |
|-------|------|
| `schema_version` | Always `"v0"` (PCS protocol version), including on `SignedScienceClaimBundle.v0` |
| `science_claim_bundle` | Nested certified `ScienceClaimBundle.v0` from LabTrust |
| Nested bundle shape | `runtime_receipts` (array) and `certificates` (array) only — never PF legacy top-level `runtime_receipt`, `trace_certificate`, or `trace_certificates` on the pending/certified bundle |

LabTrust does not adapt exports to Provability Fabric’s older local schema; PF must consume pcs-core canonical `ScienceClaimBundle.v0`.

Invalid-run `RuntimeReceipt.v0` files use `status: RuntimeObserved` with `run_outcome: failed` and `final_reason_code` set to `missing_qc` or `unauthorized_release` so downstream UIs can explain failures without overloading artifact status.

## 10. Step 7: import into Scientific Memory

```bash
just pcs-import-bundle BUNDLE=signed_science_claim_bundle.json
just pcs-render-claim CLAIM_ID=<claim_id>
```

Use `claim_id` from the signed bundle (`claim-pcs-qc-release-v0.1` in the demo). Scientific Memory imports **`SignedScienceClaimBundle.v0`**, not the pending bundle alone.

## 11. Expected output files

| Path | Artifact |
|------|----------|
| `trace.json` | Hash-chained workflow trace |
| `runtime_receipt.json` | `RuntimeReceipt.v0` |
| `runs/qc-release/pcs/evidence_bundle.json` | `EvidenceBundle.v0` |
| `science_claim_bundle.pending.json` | Pending `ScienceClaimBundle.v0` |
| `science_claim_bundle.certified.json` | Certified bundle |
| `trace_certificate.json` | `TraceCertificate.v0` |
| `signed_science_claim_bundle.json` | `SignedScienceClaimBundle.v0` (PF output) |

Golden references: `examples/pcs_qc_release/expected/` (regenerate with `python examples/pcs_qc_release/scripts/generate_golden.py` from a git checkout).

### Cross-repo handoff artifacts

| Consumer | Files |
|----------|--------|
| CertifyEdge | `valid_trace.json`, `invalid_missing_qc_trace.json`, `invalid_unauthorized_trace.json` (under `expected/`), trace hash rule in [docs/pcs_export.md](../../docs/pcs_export.md) |
| Provability Fabric | `science_claim_bundle.pending.json`, `science_claim_bundle.certified.json`, `runtime_receipt.json`, `trace_certificate.json` |
| Scientific Memory | `signed_science_claim_bundle.json`, `claim_id`, limitations in [docs/pcs_limitations.md](../../docs/pcs_limitations.md) |

## 12. Troubleshooting

- **`pcs validate` fails:** Install pcs-core; ensure digests use `sha256:` prefix and `schema_version` is `v0`.
- **trace_hash mismatch:** Re-export trace and receipt from the same `run_dir`; do not edit events after export.
- **`local_dev: true` on receipts:** Normal when not in a git checkout (`source_commit: local-dev`). Golden fixtures use `--deterministic` / `PCS_DETERMINISTIC=1` instead (frozen `source_commit`, no `local_dev`).
- **attach-certificate fails:** Certificate `trace_hash` must match `runtime_receipt.trace_hash`.
- **Invalid demos pass release:** Check `policy/pcs/roles.yaml`; only `release_manager` is `release_capable`.

## 13. Limitations

- Simulation only; no real LIS/hospital integration.
- No clinical safety or regulatory claims.
- Trace model is LabTrust-specific; PCS bundles follow pcs-core schemas.
- Certification and signing require external repos and are not bundled in LabTrust-Gym CI by default.

See also [docs/pcs_limitations.md](../../docs/pcs_limitations.md).
