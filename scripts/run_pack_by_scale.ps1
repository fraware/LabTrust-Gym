# Run the coordination security pack one scale at a time to reduce runtime per job.
# Each scale writes to its own output directory. Use the same --matrix-preset full_matrix
# (all methods, all injections) but restrict to a single scale via --scale-ids.
#
# Usage (run one scale):
#   .\scripts\run_pack_by_scale.ps1 -Scale small_smoke
#   .\scripts\run_pack_by_scale.ps1 -Scale medium_stress_signed_bus
#   .\scripts\run_pack_by_scale.ps1 -Scale corridor_heavy
#
# Usage (run all three scales in sequence to separate dirs):
#   .\scripts\run_pack_by_scale.ps1 -RunAll
#
# Usage (custom base dir and workers):
#   .\scripts\run_pack_by_scale.ps1 -Scale small_smoke -OutBase "pack_run" -Workers 8
#
# To build the risk register from all three scale runs:
#   labtrust export-risk-register --out risk_register_out --runs pack_run_full_matrix/small_smoke --runs pack_run_full_matrix/medium_stress_signed_bus --runs pack_run_full_matrix/corridor_heavy

param(
    [ValidateSet("small_smoke", "medium_stress_signed_bus", "corridor_heavy")]
    [string] $Scale = "",
    [switch] $RunAll,
    [string] $OutBase = "",
    [int] $Workers = 8,
    [int] $Seed = 42
)

$ErrorActionPreference = "Stop"
$Workers = [Math]::Min(61, [Math]::Max(1, $Workers))
$RepoRoot = if ($env:REPO_ROOT) { $env:REPO_ROOT } else { (Get-Item $PSScriptRoot).Parent.FullName }
if (-not $OutBase) { $OutBase = Join-Path $RepoRoot "pack_run_full_matrix" }

$PythonExe = (Get-Command python -ErrorAction Stop).Source

function Run-OneScale {
    param([string] $ScaleId)
    $OutDir = Join-Path $OutBase $ScaleId
    Write-Host "Running pack for scale: $ScaleId (out: $OutDir, workers: $Workers)"
    Push-Location $RepoRoot
    try {
        & $PythonExe -m labtrust_gym.cli.main run-coordination-security-pack `
            --out $OutDir `
            --matrix-preset full_matrix `
            --scale-ids $ScaleId `
            --seed $Seed `
            --workers $Workers
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
    Write-Host "Done: $ScaleId"
}

if ($RunAll) {
    Run-OneScale -ScaleId "small_smoke"
    Run-OneScale -ScaleId "medium_stress_signed_bus"
    Run-OneScale -ScaleId "corridor_heavy"
    Write-Host "All three scales finished. Outputs under $OutBase"
    exit 0
}

if (-not $Scale) {
    Write-Host "Usage:"
    Write-Host "  Run one scale:  .\scripts\run_pack_by_scale.ps1 -Scale small_smoke"
    Write-Host "  Run one scale:  .\scripts\run_pack_by_scale.ps1 -Scale medium_stress_signed_bus"
    Write-Host "  Run one scale:  .\scripts\run_pack_by_scale.ps1 -Scale corridor_heavy"
    Write-Host "  Run all three:  .\scripts\run_pack_by_scale.ps1 -RunAll"
    Write-Host ""
    Write-Host "Equivalent labtrust commands (same effect, run from repo root):"
    Write-Host "  # Scale 1: small_smoke (4 agents, fastest)"
    Write-Host "  python -m labtrust_gym.cli.main run-coordination-security-pack --out pack_run_full_matrix/small_smoke --matrix-preset full_matrix --scale-ids small_smoke --seed 42 --workers 8"
    Write-Host ""
    Write-Host "  # Scale 2: medium_stress_signed_bus (75 agents)"
    Write-Host "  python -m labtrust_gym.cli.main run-coordination-security-pack --out pack_run_full_matrix/medium_stress_signed_bus --matrix-preset full_matrix --scale-ids medium_stress_signed_bus --seed 42 --workers 8"
    Write-Host ""
    Write-Host "  # Scale 3: corridor_heavy (200 agents)"
    Write-Host "  python -m labtrust_gym.cli.main run-coordination-security-pack --out pack_run_full_matrix/corridor_heavy --matrix-preset full_matrix --scale-ids corridor_heavy --seed 42 --workers 8"
    exit 0
}

Run-OneScale -ScaleId $Scale
