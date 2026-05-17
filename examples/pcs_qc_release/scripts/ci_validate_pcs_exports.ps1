# CI: deterministic PCS export + pcs-core validation (same as ci_validate_pcs_exports.py).
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"

$Python = Get-PcsTool "python"
& $Python examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
