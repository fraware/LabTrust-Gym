# PCS QC-release demonstration

LabTrust-Gym v0.1 flagship demo: simulate a hospital lab QC-release workflow, emit hash-chained traces, and export PCS artifacts validated by [pcs-core](https://github.com/SentinelOps-CI/pcs-core).

## Quick start

```bash
pip install -e ".[dev]"
# optional: pip install -e ../pcs-core/python

labtrust run-demo qc-release
labtrust export-trace --run runs/qc-release --out trace.json
labtrust export-runtime-receipt --run runs/qc-release --out runtime_receipt.json
labtrust export-pcs --run runs/qc-release --out science_claim_bundle.pending.json
```

Invalid scenarios:

```bash
labtrust run-demo qc-release-invalid-missing-qc
labtrust run-demo qc-release-invalid-unauthorized
```

See [RUNBOOK.md](RUNBOOK.md) for the full end-to-end flow (CertifyEdge, Provability Fabric, Scientific Memory).

## Files

| File | Purpose |
|------|---------|
| `valid_workflow.yaml` | Accession → QC → analysis → release (authorized) |
| `invalid_missing_qc.yaml` | Release without QC (`missing_qc`) |
| `invalid_unauthorized_release.yaml` | Release by `unauthorized_user` |
| `expected/` | Golden traces, receipts, and bundles for CI |
| `scripts/run_e2e_local.sh` | Local smoke script |

Policy: `policy/pcs/` (`roles.yaml`, `reason_codes.yaml`, `qc_release_policy.yaml`).
