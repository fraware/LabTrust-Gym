# Refresh LabTrust flat benchmark + pcs-core pcs-bench canonical suite (single producer run).
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"

$Python = Get-PcsTool "python"
$Labtrust = Get-PcsTool "labtrust"

& $Labtrust generate-benchmark-cases `
    --workflow hospital_lab.qc_release `
    --out examples/pcs_qc_release/benchmark `
    --release-dir examples/pcs_qc_release/release `
    --seed 42
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_cases.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& (Join-Path $PSScriptRoot "export_pcs_bench_to_pcs_core.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/generate_benchmark_packet.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_ingest_golden.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "PCS benchmark fixtures refreshed (LabTrust examples + pcs-core suite + ingest CI)"
