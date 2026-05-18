# Regenerate the full LabTrust PCS Phase 2 protocol package (not mirror-only sync).
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $Root

$env:PCS_DETERMINISTIC = "1"
$env:PCS_RELEASE_FIXTURE = "1"

$Release = if ($env:PCS_RELEASE_DIR) { $env:PCS_RELEASE_DIR } else { Join-Path $Root "examples\pcs_qc_release\release" }
$PcsCore = if ($env:PCS_CORE_PATH) { $env:PCS_CORE_PATH } else { Join-Path (Split-Path $Root -Parent) "pcs-core" }
if ((Split-Path -Leaf $PcsCore) -eq "python") { $PcsCore = Split-Path $PcsCore -Parent }
$CeBin = if ($env:CERTIFYEDGE_BIN) { $env:CERTIFYEDGE_BIN } else { "certifyedge" }

$venvLabtrust = Join-Path $Root ".venv-pcs\Scripts\labtrust.exe"
if (-not (Get-Command labtrust -ErrorAction SilentlyContinue) -and (Test-Path $venvLabtrust)) {
    $env:PATH = "$(Split-Path $venvLabtrust -Parent);$env:PATH"
}

labtrust regenerate-release-protocol `
    --out $Release `
    --certifyedge-bin $CeBin `
    --pcs-core $PcsCore `
    --summary-out (Join-Path $Release "protocol_regeneration_summary.json")

labtrust check-status-policy --release-dir $Release --json

labtrust verify-release-protocol `
    --release-dir $Release `
    --pcs-core (Join-Path $PcsCore "examples\labtrust-release")

Write-Host "OK LabTrust protocol package at $Release"
