# PCS v0.1 clean-checkout chain

PCS v0.1 is **release-ready** when this chain succeeds from a clean LabTrust-Gym checkout with sibling repositories installed.

## Prerequisites

| Tool | Install |
|------|---------|
| LabTrust-Gym | `scripts/setup_pcs_dev.ps1` or `.sh` (`.venv-pcs` + pcs-core) |
| pcs-core | `pip install -e ../pcs-core/python` |
| CertifyEdge | Sibling `../CertifyEdge` or `CERTIFYEDGE_ROOT` |
| Provability Fabric | `pf` on PATH or `PF_BIN` |
| Scientific Memory | Sibling `../scientific-memory` + `just` |

## One-command chain

From **LabTrust-Gym repo root**:

```bash
export PCS_DETERMINISTIC=1
bash examples/pcs_qc_release/scripts/run_pcs_v01_clean_chain.sh
```

```powershell
$env:PCS_DETERMINISTIC = "1"
& examples/pcs_qc_release/scripts/run_pcs_v01_clean_chain.ps1
```

LabTrust-only (no CertifyEdge/PF/SM):

```bash
bash examples/pcs_qc_release/scripts/run_pcs_v01_clean_chain.sh --labtrust-only
```

## Manual chain (canonical commands)

Artifacts are written to the **repo root** by default (`PCS_CHAIN_WORK=.`) .

### LabTrust-Gym

```bash
PCS_DETERMINISTIC=1 labtrust run-demo qc-release
PCS_DETERMINISTIC=1 labtrust run-demo qc-release-invalid-missing-qc
PCS_DETERMINISTIC=1 labtrust run-demo qc-release-invalid-unauthorized

labtrust export-trace --run runs/qc-release --out trace.json
labtrust export-runtime-receipt --run runs/qc-release --out runtime_receipt.json
labtrust export-pcs --run runs/qc-release --out science_claim_bundle.pending.json
pcs validate science_claim_bundle.pending.json
```

### CertifyEdge

```bash
certifyedge emit-pcs-certificate \
  --spec templates/hospital_lab/qc_release.stl \
  --trace trace.json \
  --out trace_certificate.json
pcs validate trace_certificate.json
certifyedge verify-certificate trace_certificate.json --trace trace.json
```

Run from `CERTIFYEDGE_ROOT` or set `CERTIFYEDGE_SPEC` to an absolute path.

### LabTrust-Gym (attach)

```bash
labtrust attach-certificate \
  --bundle science_claim_bundle.pending.json \
  --certificate trace_certificate.json \
  --out science_claim_bundle.certified.json
pcs validate science_claim_bundle.certified.json
```

### Provability Fabric

```bash
pf verify science-claim science_claim_bundle.certified.json \
  --out verification_result.json
pcs validate verification_result.json

pf sign science-claim science_claim_bundle.certified.json \
  --out signed_science_claim_bundle.json
pcs validate signed_science_claim_bundle.json
pf inspect science-claim signed_science_claim_bundle.json
```

### Scientific Memory

```bash
cd ../scientific-memory
just pcs-import-bundle ../LabTrust-Gym/signed_science_claim_bundle.json
just pcs-render-claim claim-pcs-qc-release-v0.1
```

Scientific Memory `just` recipes take **positional** arguments (`bundle`, `claim_id`), not `BUNDLE=` / `CLAIM_ID=` make-style variables.

## Post-chain validation

```bash
python examples/pcs_qc_release/scripts/verify_pcs_v01_chain.py --work . --stage full
```

## Environment overrides

| Variable | Default |
|----------|---------|
| `PCS_DETERMINISTIC` | `1` |
| `PCS_CHAIN_WORK` | LabTrust repo root |
| `RUN_DIR` | `runs/qc-release` |
| `CERTIFYEDGE_ROOT` | `../CertifyEdge` |
| `CERTIFYEDGE_BIN` | `certifyedge` (if unset, prefers `$CERTIFYEDGE_ROOT/target/{debug,release}/certifyedge` over PATH) |
| `CERTIFYEDGE_SPEC` | `$CERTIFYEDGE_ROOT/templates/hospital_lab/qc_release.stl` |
| `PROVABILITY_FABRIC_ROOT` | `../provability-fabric` |
| `PF_BIN` | `pf` (if unset, prefers `$PROVABILITY_FABRIC_ROOT/core/cli/pf/pf` over PATH) |
| `SCIENTIFIC_MEMORY_ROOT` | `../scientific-memory` |
| `CLAIM_ID` | `claim-pcs-qc-release-v0.1` |
| `PCS_COPY_TO_RELEASE` | `0` (set `1` to copy outputs into `examples/pcs_qc_release/release/`) |

See also [examples/pcs_qc_release/RUNBOOK.md](../examples/pcs_qc_release/RUNBOOK.md).
