# Generate LabTrust pcs-bench suite into sibling pcs-core and sync registry.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"

$Python = Get-PcsTool "python"
$PcsCore = if ($env:PCS_CORE_PATH) { $env:PCS_CORE_PATH } else { Join-Path (Split-Path $Root -Parent) "pcs-core" }
$Out = Join-Path $PcsCore "benchmarks\labtrust-qc-release"
$Registry = Join-Path $PcsCore "examples\benchmark_registry.valid.json"

if (-not (Test-Path $PcsCore)) {
    Write-Error "pcs-core not found at $PcsCore (set PCS_CORE_PATH)"
}

& $Python examples/pcs_qc_release/scripts/generate_pcs_bench_suite.py `
    --out $Out `
    --registry $Registry `
    --fixture-root benchmarks/labtrust-qc-release `
    --seed 42
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_registry_expected.py `
    --registry $Registry
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "pcs-bench suite exported to $Out (registry: $Registry)"
