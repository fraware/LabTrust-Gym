# PCS QC-release demonstration

LabTrust-Gym v0.1 flagship demo: simulate a hospital lab QC-release workflow, emit hash-chained traces, and export PCS artifacts validated by [pcs-core](https://github.com/SentinelOps-CI/pcs-core).

## Quick start (recommended: isolated venv)

Installing into **global Python** alongside other tools (MCP, corridor-os, crewai, etc.) often triggers pip dependency conflict warnings. Use the setup script instead:

**Windows (PowerShell):**

```powershell
.\scripts\setup_pcs_dev.ps1
.\.venv-pcs\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
bash scripts/setup_pcs_dev.sh
source .venv-pcs/bin/activate
```

If pcs-core is not at `../pcs-core/python`:

```powershell
$env:PCS_CORE_PATH = "C:\Users\mateo\pcs-core\python"
.\scripts\setup_pcs_dev.ps1
```

Then:

```bash
pytest tests/pcs -q
labtrust run-demo qc-release
labtrust export-trace --run runs/qc-release --out trace.json
labtrust export-runtime-receipt --run runs/qc-release --out runtime_receipt.json
labtrust export-pcs --run runs/qc-release --out science_claim_bundle.pending.json
labtrust validate-pcs --run runs/qc-release
labtrust export-pcs-handoff --out handoff/
```

Trace/event model: [docs/pcs_trace_model.md](../../docs/pcs_trace_model.md).

Regenerate golden snapshots (uses `PCS_DETERMINISTIC=1`; no git HEAD required):

```bash
python examples/pcs_qc_release/scripts/generate_golden.py
```

LabTrust-only smoke (valid + invalid demos, export, `pcs validate`, golden check):

```bash
bash examples/pcs_qc_release/scripts/labtrust_only_smoke.sh
# Windows:
# .\examples\pcs_qc_release\scripts\labtrust_only_smoke.ps1
```

### Manual install (same venv)

```bash
python -m venv .venv-pcs
# activate venv, then:
pip install -e /path/to/pcs-core/python
pip install -e ".[dev,pcs]"
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
| `expected/` | Golden traces, receipts, bundles, `trace_certificate.v0.json` (pcs-core validated in CI) |
| `scripts/run_e2e_local.sh` | Local smoke (`PCS_DETERMINISTIC=1`) |
| `scripts/labtrust_only_smoke.sh` / `.ps1` | One-command LabTrust-only smoke |
| `scripts/generate_golden.py` | Regenerate `expected/` (deterministic fixtures) |

Policy: `policy/pcs/` (`roles.yaml`, `reason_codes.yaml`, `qc_release_policy.yaml`).
