# One-shot PCS dev setup + smoke. Run from any cwd, e.g.:
#   & "C:\Users\mateo\LabTrust-Gym\examples\pcs_qc_release\scripts\setup_and_smoke.ps1"
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root

& (Join-Path $Root "scripts\setup_pcs_dev.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& (Join-Path $PSScriptRoot "run_pcs_ci_local.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
