# PCS QC-release quickstart

Proof-Carrying Science (PCS) demonstrates how a simulated hospital lab workflow produces versioned artifacts that validate with [pcs-core](https://github.com/SentinelOps-CI/pcs-core).

Full step-by-step commands live in the repository under `examples/pcs_qc_release/`. This page is the documentation-site entry point.

## Setup

**Windows (PowerShell)** from the repository root.

```powershell
.\scripts\setup_pcs_dev.ps1
.\.venv-pcs\Scripts\Activate.ps1
```

**Linux/macOS.**

```bash
bash scripts/setup_pcs_dev.sh
source .venv-pcs/bin/activate
```

When pcs-core lives outside `../pcs-core/python`, set `PCS_CORE_PATH` before running the setup script.

## Smoke test

```bash
pytest tests/pcs -q
labtrust run-demo qc-release
labtrust export-trace --run runs/qc-release --out trace.json
labtrust export-runtime-receipt --run runs/qc-release --out runtime_receipt.json
labtrust export-pcs --run runs/qc-release --out science_claim_bundle.pending.json
labtrust validate-pcs --run runs/qc-release
```

## In-repo CI gate

```bash
bash examples/pcs_qc_release/scripts/run_pcs_ci_local.sh
```

This script matches `.github/workflows/pcs.yml`. See the [PCS overview](../pcs/index.md).

## Next steps

| Topic | Document |
|-------|----------|
| Operator runbook | [PCS operator runbook](pcs_qc_release-operator.md) |
| Cross-repo release chain | [PCS release gate](../pcs_v01_clean_chain.md) |
| Extend a second workflow | [Extending PCS workflows](../pcs/extending-workflows.md) |
| PCS overview | [PCS index](../pcs/index.md) |

Repository copies are available under [examples/pcs_qc_release](https://github.com/fraware/LabTrust-Gym/tree/main/examples/pcs_qc_release) on GitHub.
