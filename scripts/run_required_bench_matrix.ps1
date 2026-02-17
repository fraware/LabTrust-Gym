# Required-bench coverage pack (plan-driven): enumerate required cells from method_risk_matrix,
# join with required_bench_plan.v0.1.yaml, run minimal distinct runs, then export-risk-register
# and validate-coverage --strict.
#
# Usage: .\scripts\run_required_bench_matrix.ps1 [-OutDir path]
#   -OutDir  output directory (default: runs/required_bench_pack)
# Env: SEED_BASE (default 42)
# Exit: 0 if validate-coverage --strict passes; 1 if plan incomplete or validate-coverage fails.

param([string]$OutDir)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "runs" "required_bench_pack" }
$SeedBase = if ($env:SEED_BASE) { $env:SEED_BASE } else { "42" }
$env:LABTRUST_ALLOW_NETWORK = if ($env:LABTRUST_ALLOW_NETWORK) { $env:LABTRUST_ALLOW_NETWORK } else { "0" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Set-Location $RepoRoot

[string[]]$LabtrustCmd = if (Get-Command labtrust -ErrorAction SilentlyContinue) { "labtrust" } else { "python", "-m", "labtrust_gym.cli.main" }
function Run-Labtrust { param([string[]]$A); if ($LabtrustCmd.Length -eq 1) { & $LabtrustCmd[0] @A } else { & $LabtrustCmd[0] @($LabtrustCmd[1..($LabtrustCmd.Length-1)] + $A) }; if ($LASTEXITCODE -ne 0) { throw "labtrust failed" } }

# Enumerate distinct runs from plan
$RunsList = Join-Path $OutDir ".plan_runs.txt"
python scripts/required_bench_plan_runs.py | Set-Content -Path $RunsList -Encoding utf8
if ($LASTEXITCODE -ne 0) { exit 1 }

$RunDirs = [System.Collections.ArrayList]@()
Get-Content $RunsList -Encoding utf8 | ForEach-Object {
  $line = $_.Trim()
  if (-not $line) { return }
  $parts = $line -split "\s+"
  if ($parts[0] -eq "security_suite") {
    $SecurityDir = Join-Path $OutDir "security_smoke"
    New-Item -ItemType Directory -Force -Path $SecurityDir | Out-Null
    Write-Host "=== run: security_suite ==="
    Run-Labtrust "run-security-suite", "--out", $SecurityDir, "--seed", $SeedBase
    [void]$RunDirs.Add($SecurityDir)
    return
  }
  if ($parts[0] -eq "coord_risk" -and $parts.Length -ge 4) {
    $methodId = $parts[1]
    $injectionId = $parts[2]
    $suffix = $parts[3] -replace "-", "_" -replace "\.", "_"
    $runDir = Join-Path $OutDir "coord_$suffix"
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    Write-Host "=== run: coord_risk $methodId $injectionId ==="
    Run-Labtrust "run-benchmark", "--task", "coord_risk", "--coord-method", $methodId, "--injection", $injectionId, "--scale", "small_smoke", "--episodes", "1", "--seed", $SeedBase, "--out", $runDir
    [void]$RunDirs.Add($runDir)
  }
}

$RunsArgs = @("export-risk-register", "--out", $OutDir)
foreach ($d in $RunDirs) { $RunsArgs += "--runs"; $RunsArgs += $d }

Write-Host "=== export-risk-register + validate-coverage --strict ==="
if ($RunDirs.Count -eq 0) {
  Write-Host "No run dirs from plan (empty plan?). Running security smoke + coord pack fallback."
  $SecurityDir = Join-Path $OutDir "security_smoke"
  $CoordDir = Join-Path $OutDir "coord_pack"
  New-Item -ItemType Directory -Force -Path $SecurityDir, $CoordDir | Out-Null
  Run-Labtrust "run-security-suite", "--out", $SecurityDir, "--seed", $SeedBase
  Run-Labtrust "run-coordination-security-pack", "--out", $CoordDir, "--seed", $SeedBase, "--methods-from", "fixed", "--injections-from", "critical"
  Run-Labtrust "export-risk-register", "--out", $OutDir, "--runs", $SecurityDir, "--runs", $CoordDir
} else {
  Run-Labtrust $RunsArgs
}

$Bundle = Join-Path $OutDir "RISK_REGISTER_BUNDLE.v0.1.json"
if (-not (Test-Path $Bundle)) { Write-Error "Bundle not written: $Bundle"; exit 1 }

Run-Labtrust "validate-coverage", "--strict", "--bundle", $Bundle, "--out", $OutDir
Write-Host "Required-bench coverage pack written to $OutDir. validate-coverage --strict passed."
