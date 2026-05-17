# LabTrust-only PCS QC-release smoke. Safe to run from any cwd (uses repo root + .venv-pcs).
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"

$Labtrust = Get-PcsTool "labtrust"
$Pcs = Get-PcsTool "pcs"
$Python = Get-PcsTool "python"

$RunDir = if ($env:RUN_DIR) { $env:RUN_DIR } else { "runs/qc-release" }
$TraceOut = Join-Path $Root "trace.json"
$ReceiptOut = Join-Path $Root "runtime_receipt.json"
$BundleOut = Join-Path $Root "science_claim_bundle.pending.json"

function Assert-LastExitCode {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed (exit $LASTEXITCODE)"
    }
}

& $Labtrust run-demo qc-release --deterministic --out $RunDir
Assert-LastExitCode "run-demo qc-release"
& $Labtrust run-demo qc-release-invalid-missing-qc --deterministic
Assert-LastExitCode "run-demo qc-release-invalid-missing-qc"
& $Labtrust run-demo qc-release-invalid-unauthorized --deterministic
Assert-LastExitCode "run-demo qc-release-invalid-unauthorized"

& $Labtrust export-trace --run $RunDir --out $TraceOut
Assert-LastExitCode "export-trace"
& $Labtrust export-runtime-receipt --run $RunDir --out $ReceiptOut
Assert-LastExitCode "export-runtime-receipt"
& $Labtrust export-pcs --run $RunDir --out $BundleOut
Assert-LastExitCode "export-pcs"

if (-not (Test-Path $ReceiptOut)) { throw "Missing export: $ReceiptOut" }
if (-not (Test-Path $BundleOut)) { throw "Missing export: $BundleOut" }

& $Pcs validate $ReceiptOut
Assert-LastExitCode "pcs validate runtime_receipt"
& $Pcs validate $BundleOut
Assert-LastExitCode "pcs validate science_claim_bundle.pending"

& $Python -m pytest tests/pcs/test_golden_deterministic.py::test_deterministic_mode_reproduces_expected_artifacts -q
Assert-LastExitCode "pytest golden determinism"

Write-Host "LabTrust-only PCS smoke OK (run=$RunDir)"
