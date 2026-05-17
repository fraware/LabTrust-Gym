# Isolated PCS dev environment (avoids global pip dependency conflicts).
# Usage: .\scripts\setup_pcs_dev.ps1              # PCS tests only (tests/pcs)
#        .\scripts\setup_pcs_dev.ps1 -IncludeEnv  # + PettingZoo for full pytest
#        $env:PCS_CORE_PATH = "C:\path\to\pcs-core\python"  # optional override

param(
    [switch]$IncludeEnv
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Venv = Join-Path $Root ".venv-pcs"
$PcsCore = if ($env:PCS_CORE_PATH) { $env:PCS_CORE_PATH } else { Join-Path (Split-Path -Parent $Root) "pcs-core\python" }

if (-not (Test-Path $PcsCore)) {
    Write-Host "pcs-core not found at: $PcsCore" -ForegroundColor Red
    Write-Host "Set PCS_CORE_PATH to your pcs-core/python directory, e.g.:" -ForegroundColor Yellow
    Write-Host '  $env:PCS_CORE_PATH = "C:\Users\mateo\pcs-core\python"' -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $Venv)) {
    python -m venv $Venv
}
$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

& $Python -m pip install -U pip wheel
& $Pip install -e $PcsCore
if ($IncludeEnv) {
    & $Pip install -e ".[dev,env,pcs]"
} else {
    & $Pip install -e ".[dev,pcs]"
}
& $Pip install "referencing>=0.35.0,<0.37.0"

Write-Host ""
Write-Host "PCS dev environment ready." -ForegroundColor Green
Write-Host "Activate:  $($Venv)\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host "Then run:  pytest tests/pcs -q" -ForegroundColor Cyan
Write-Host "           labtrust run-demo qc-release" -ForegroundColor Cyan
if ($IncludeEnv) {
    Write-Host "Full suite: pytest -q" -ForegroundColor Cyan
} else {
    Write-Host "Full suite needs env: .\scripts\setup_pcs_dev.ps1 -IncludeEnv" -ForegroundColor Yellow
}
