# Quickstart: install -> validate-policy -> quick-eval -> paper artifact -> verify-bundle.
# Run from repo root. For v0.1.0 release reproducibility.
# Note: Paths with spaces or special characters may require quoting or a different workdir; see docs/GETTING_STARTED_FORKER.md.

$ErrorActionPreference = "Stop"
$RepoRoot = if ($env:REPO_ROOT) { $env:REPO_ROOT } else { (Get-Item $PSScriptRoot).Parent.FullName }
Set-Location $RepoRoot

Write-Host "=== 1. Install ==="
if (-not (Get-Command pip -ErrorAction SilentlyContinue)) { Write-Error "pip not found. Install Python and ensure pip is on PATH."; exit 1 }
pip install -e ".[dev,env,plots]" -q
if (-not (Get-Command labtrust -ErrorAction SilentlyContinue)) { Write-Error "labtrust not found after install. Try: python -m labtrust_gym.cli.main --version"; exit 1 }
labtrust --version

Write-Host "=== 2. Validate policy ==="
labtrust validate-policy

Write-Host "=== 3. Quick-eval (TaskA, TaskD, TaskE) ==="
labtrust quick-eval --seed 42

Write-Host "=== 4. Paper artifact (paper_v0.1) ==="
$Out = if ($env:OUT) { $env:OUT } else { "./labtrust_paper_v0.1" }
labtrust package-release --profile paper_v0.1 --seed-base 100 --out $Out

Write-Host "=== 5. Verify evidence bundle ==="
$BundleDir = Get-ChildItem -Path $Out -Recurse -Directory -Filter "EvidenceBundle.v0.1" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($BundleDir -and (Test-Path $BundleDir.FullName)) {
  labtrust verify-bundle --bundle $BundleDir.FullName
  Write-Host "Verify-bundle passed."
} else {
  Write-Host "No EvidenceBundle.v0.1 dir found under $Out; skip verify-bundle."
}

Write-Host "=== Quickstart done ==="
