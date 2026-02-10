# Forker quickstart: validate-policy, run coordination pack (fixed + critical), build report, export risk register.
# Usage: .\scripts\forker_quickstart.ps1 [OUT_DIR]
#   OUT_DIR defaults to .\labtrust_runs\forker_quickstart_<timestamp>

$ErrorActionPreference = "Stop"
$RepoRoot = if ($env:REPO_ROOT) { $env:REPO_ROOT } else { (Get-Location).Path }
if (-not (Split-Path -IsAbsolute $RepoRoot)) {
  $RepoRoot = Join-Path (Get-Location) $RepoRoot
}
Set-Location $RepoRoot

$Out = $args[0]
if (-not $Out) {
  $Out = ".\labtrust_runs\forker_quickstart_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
}

$Labtrust = if (Get-Command labtrust -ErrorAction SilentlyContinue) {
  @("labtrust")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  @("python", "-m", "labtrust_gym.cli.main")
} else {
  Write-Error "Install the package (pip install -e \".[dev,env]\") and ensure labtrust or python is on PATH."
  exit 1
}

Write-Host "=== Forker quickstart (out=$Out) ==="
& $Labtrust[0] $Labtrust[1..($Labtrust.Length-1)] forker-quickstart --out $Out
Write-Host "Done. COORDINATION_DECISION and risk register under $Out"
