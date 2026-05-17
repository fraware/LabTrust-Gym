# LabTrust-only PCS QC-release smoke (requires pcs-core: scripts\setup_pcs_dev.ps1)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"

$RunDir = if ($env:RUN_DIR) { $env:RUN_DIR } else { "runs/qc-release" }

labtrust run-demo qc-release --deterministic --out $RunDir
labtrust run-demo qc-release-invalid-missing-qc --deterministic
labtrust run-demo qc-release-invalid-unauthorized --deterministic

labtrust export-trace --run $RunDir --out trace.json
labtrust export-runtime-receipt --run $RunDir --out runtime_receipt.json
labtrust export-pcs --run $RunDir --out science_claim_bundle.pending.json

pcs validate runtime_receipt.json
pcs validate science_claim_bundle.pending.json

python -m pytest tests/pcs/test_golden_deterministic.py -q
Write-Host "LabTrust-only PCS smoke OK (run=$RunDir)"
