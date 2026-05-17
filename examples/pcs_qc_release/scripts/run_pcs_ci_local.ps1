# Full PCS CI parity locally (matches .github/workflows/pcs.yml).
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"

$Python = Get-PcsTool "python"

& $Python -m pytest tests/pcs -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python examples/pcs_qc_release/scripts/ci_validate_release_fixtures.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "PCS local CI OK"
