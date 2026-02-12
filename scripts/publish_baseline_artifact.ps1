# Create a zip of the canonical baseline for publishing (e.g. Zenodo).
# Usage: .\scripts\publish_baseline_artifact.ps1 [OUTPUT_ZIP]
# Default: labtrust_baselines_v0.2_<YYYYMMDD>.zip in repo root.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $RepoRoot "policy"))) {
    $RepoRoot = (Get-Location).Path
}
$BaselineDir = Join-Path $RepoRoot "benchmarks\baselines_official\v0.2"
if (-not (Test-Path $BaselineDir)) {
    Write-Error "Missing $BaselineDir. Run: labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force"
    exit 1
}
$Date = if ($args[0]) { $args[0] } else { Get-Date -Format "yyyyMMdd" }
$OutZip = if ($Date -match '\.zip$') { $Date } else { "labtrust_baselines_v0.2_$Date.zip" }
$OutPath = Join-Path $RepoRoot $OutZip
Write-Host "Creating $OutZip from $BaselineDir..."
Compress-Archive -Path $BaselineDir -DestinationPath $OutPath -Force
Write-Host "Done: $OutPath"
Write-Host "To publish: upload to Zenodo or similar; cite this repo and the regenerate command in README.md inside the zip."
