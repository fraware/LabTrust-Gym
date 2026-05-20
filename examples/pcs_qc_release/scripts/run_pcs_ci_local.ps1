# Full PCS CI parity locally (matches .github/workflows/pcs.yml).
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"

$Python = Get-PcsTool "python"
$Labtrust = Get-PcsTool "labtrust"

& $Python -m pytest tests/pcs -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_workflow_profile.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_release_fixtures.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_regeneration_report.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_failure_manifests.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_formalization.py
& $Labtrust generate-benchmark-cases `
  --workflow hospital_lab.qc_release `
  --out examples/pcs_qc_release/benchmark `
  --release-dir examples/pcs_qc_release/release `
  --seed 42
& $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_cases.py
& $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_pcs_core.py
& $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_pcs_bench_layout.py
& $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_registry_expected.py
& $Python examples/pcs_qc_release/scripts/generate_benchmark_packet.py
& $Python examples/pcs_qc_release/scripts/ci_benchmark_reproducibility.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Labtrust check-status-policy --release-dir examples/pcs_qc_release/release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Labtrust generate-failure-gallery `
    --workflow hospital_lab.qc_release `
    --out examples/pcs_qc_release/failures `
    --release-dir examples/pcs_qc_release/release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/validate_failure_gallery.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$PcsCore = if ($env:PCS_CORE_PATH) { $env:PCS_CORE_PATH } else { Join-Path (Split-Path $Root -Parent) "pcs-core" }
$Canon = Join-Path $PcsCore "examples\labtrust-release"
if (Test-Path (Join-Path $Canon "trace.json")) {
    & $Labtrust verify-release-protocol `
        --release-dir examples/pcs_qc_release/release `
        --pcs-core $Canon
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "PCS local CI OK"
