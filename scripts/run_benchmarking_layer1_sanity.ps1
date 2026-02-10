# Layer 1 - Sanity: TaskG (S scale, 3 seeds) + TaskH (S scale, 1 injection, 3 seeds)
# for SOTA methods + baselines. Override via LABTRUST_SANITY_METHODS.
# Set LABTRUST_SANITY_FULL=1 to run TaskG + TaskH(none) for every method from policy.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }
Set-Location $RepoRoot

$OutDir = if ($env:OUT_DIR) { $env:OUT_DIR } else { "labtrust_runs/sota_sanity" }
$TaskGSeed = if ($env:TASKG_SEED) { $env:TASKG_SEED } else { "100" }
$TaskHSeed = if ($env:TASKH_SEED) { $env:TASKH_SEED } else { "200" }
$Injection = if ($env:INJECTION) { $env:INJECTION } else { "INJ-COMMS-POISON-001" }

if ($env:LABTRUST_SANITY_FULL -eq "1") {
  $MethodsStr = python -c "from pathlib import Path; from labtrust_gym.policy.coordination import load_coordination_methods; r = load_coordination_methods(Path('policy/coordination/coordination_methods.v0.1.yaml')); print(' '.join(m for m in sorted(r.keys()) if m != 'marl_ppo'))"
} else {
  $MethodsStr = if ($env:LABTRUST_SANITY_METHODS) { $env:LABTRUST_SANITY_METHODS } else { "kernel_whca market_auction ripple_effect group_evolving_experience_sharing" }
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Methods = $MethodsStr -split '\s+'

foreach ($id in $Methods) {
  Write-Host "Layer1 sanity: $id TaskG..."
  & labtrust run-benchmark --task TaskG_COORD_SCALE --coord-method $id --scale small_smoke --episodes 3 --seed $TaskGSeed --out "$OutDir/${id}_taskg.json" --llm-backend deterministic
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  Write-Host "Layer1 sanity: $id TaskH $Injection..."
  & labtrust run-benchmark --task TaskH_COORD_RISK --coord-method $id --injection $Injection --scale small_smoke --episodes 3 --seed $TaskHSeed --out "$OutDir/${id}_taskh_poison.json" --llm-backend deterministic
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  if ($env:LABTRUST_SANITY_FULL -eq "1") {
    Write-Host "Layer1 sanity: $id TaskH baseline (none)..."
    & labtrust run-benchmark --task TaskH_COORD_RISK --coord-method $id --scale small_smoke --episodes 1 --seed $TaskHSeed --out "$OutDir/${id}_taskh_none.json" --llm-backend deterministic
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
}

Write-Host "Layer 1 sanity done. Output: $OutDir"
