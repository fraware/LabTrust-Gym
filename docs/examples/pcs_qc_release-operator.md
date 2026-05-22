# PCS QC-release operator runbook

This page summarizes the end-to-end Proof-Carrying Science (PCS) path for the hospital lab QC-release reference workflow. It is written for operators preparing a public or cross-repository release.

The workflow is a **research simulation** for laboratory automation benchmarks and carries no clinical deployment claims.

## What you are proving

A sample may be released only after accession, QC completion, analysis, authorization by a release-capable actor, and satisfaction of protocol constraints recorded in a hash-chained trace.

LabTrust-Gym simulates the workflow, exports runtime artifacts, and hands off to external tools for certification, verification, and signing.

## Repositories

| Repository | Role |
|------------|------|
| [LabTrust-Gym](https://github.com/fraware/LabTrust-Gym) | Workflow simulation, trace, PCS export |
| [pcs-core](https://github.com/SentinelOps-CI/pcs-core) | Schema validation, canonical hashing |
| [CertifyEdge](https://github.com/fraware/CertifyEdge) | `TraceCertificate.v0` |
| [provability-fabric](https://github.com/SentinelOps-CI/provability-fabric) | Verify and sign science claim bundles |
| [scientific-memory](https://github.com/fraware/scientific-memory) | Import and render signed claims |

## Two fixture trees (keep separate)

| Directory | Use |
|-----------|-----|
| `examples/pcs_qc_release/expected/` | LabTrust-local deterministic goldens for unit tests (may include a mock certificate) |
| `examples/pcs_qc_release/release/` | Cross-repo release evidence; must match pcs-core `examples/labtrust-release/` |

Only `release/` counts as release evidence for CertifyEdge, Provability Fabric, and Scientific Memory.

Regenerate release evidence atomically.

```bash
export PCS_DETERMINISTIC=1
bash examples/pcs_qc_release/scripts/run_pcs_v01_clean_chain.sh
# optional: PCS_COPY_TO_RELEASE=1 to copy into examples/pcs_qc_release/release/
```

You can also sync from canonical pcs-core after the chain is updated there.

```bash
python scripts/apply_pcs_core_labtrust_schema_profiles.py --pcs-core ../pcs-core
python -m labtrust_gym.pcs.sync_pcs_core_rc --pcs-core ../pcs-core/examples/labtrust-release
python -m labtrust_gym.pcs.sync_pcs_core_rc --verify-only --pcs-core ../pcs-core/examples/labtrust-release
```

## LabTrust-only segment

```bash
labtrust run-demo qc-release
labtrust run-demo qc-release-invalid-missing-qc
labtrust run-demo qc-release-invalid-unauthorized

labtrust export-trace --run runs/qc-release --out trace.json
labtrust export-runtime-receipt --run runs/qc-release --out runtime_receipt.json
labtrust export-pcs --run runs/qc-release --out science_claim_bundle.pending.json
pcs validate runtime_receipt.json
pcs validate science_claim_bundle.pending.json
```

Deterministic CI mode uses the following command.

```bash
PCS_DETERMINISTIC=1 labtrust run-demo qc-release --deterministic
```

## CertifyEdge

From CertifyEdge root (or with `CERTIFYEDGE_SPEC` set).

```bash
certifyedge emit-pcs-certificate \
  --spec templates/hospital_lab/qc_release.stl \
  --trace trace.json \
  --out trace_certificate.json
pcs validate trace_certificate.json
certifyedge verify-certificate trace_certificate.json --trace trace.json
```

## Attach certificate (LabTrust)

```bash
labtrust attach-certificate \
  --bundle science_claim_bundle.pending.json \
  --certificate trace_certificate.json \
  --out science_claim_bundle.certified.json
pcs validate science_claim_bundle.certified.json
```

## Provability Fabric

```bash
pf verify science-claim science_claim_bundle.certified.json --out verification_result.json
pf sign science-claim science_claim_bundle.certified.json --out signed_science_claim_bundle.json
```

## Scientific Memory

```bash
cd ../scientific-memory
just pcs-import-bundle ../LabTrust-Gym/signed_science_claim_bundle.json
just pcs-render-claim claim-pcs-qc-release-v0.1
```

## Validation before release

```bash
bash examples/pcs_qc_release/scripts/run_pcs_ci_local.sh
make pcs-verify   # requires sibling pcs-core
labtrust verify-release-protocol --release-dir examples/pcs_qc_release/release --pcs-core ../pcs-core/examples/labtrust-release
labtrust check-status-policy --release-dir examples/pcs_qc_release/release --json
```

## Canonical workflow id

All PCS exports use the following workflow identifier.

```text
workflow_id = hospital_lab.qc_release
```

## Related documentation

- [PCS overview](../pcs/index.md)
- [PCS release gate](../pcs_v01_clean_chain.md)
- [Export commands](../pcs_export.md)
- [Handoff bundle](../pcs_handoff.md)
- [Limitations](../pcs_limitations.md)

The full repository runbook with environment tables is [examples/pcs_qc_release/RUNBOOK.md](https://github.com/fraware/LabTrust-Gym/blob/main/examples/pcs_qc_release/RUNBOOK.md).
