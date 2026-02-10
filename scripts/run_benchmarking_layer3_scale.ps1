# Layer 3 - Scale: TaskG and TaskH at S/M/L; TaskH with top 3 injections;
# 10-30 episodes per cell; timing_mode=simulated.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }
Set-Location $RepoRoot

$OutDir = if ($env:OUT_DIR) { $env:OUT_DIR } else { "labtrust_runs/sota_scale" }
$ScalesStr = if ($env:LABTRUST_SCALE_SCALES) { $env:LABTRUST_SCALE_SCALES } else { "small_smoke medium_stress_signed_bus corridor_heavy" }
$MethodsStr = if ($env:LABTRUST_SCALE_METHODS) { $env:LABTRUST_SCALE_METHODS } else { "kernel_whca market_auction ripple_effect group_evolving_experience_sharing" }
$InjectionsStr = if ($env:LABTRUST_SCALE_INJECTIONS) { $env:LABTRUST_SCALE_INJECTIONS } else { "INJ-COMMS-POISON-001 INJ-ID-SPOOF-001 INJ-COLLUSION-001" }
$Episodes = if ($env:EPISODES) { $env:EPISODES } else { "15" }
$BaseSeed = if ($env:BASE_SEED) { $env:BASE_SEED } else { "300" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Scales = $ScalesStr -split '\s+'
$Methods = $MethodsStr -split '\s+'
$Injections = $InjectionsStr -split '\s+'

foreach ($id in $Methods) {
  foreach ($scale in $Scales) {
    Write-Host "Layer3 scale: $id TaskG scale=$scale..."
    & labtrust run-benchmark --task TaskG_COORD_SCALE --coord-method $id --scale $scale --episodes $Episodes --seed $BaseSeed --timing simulated --out "$OutDir/${id}_taskg_${scale}.json"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
  foreach ($scale in $Scales) {
    foreach ($inj in $Injections) {
      Write-Host "Layer3 scale: $id TaskH scale=$scale injection=$inj..."
      & labtrust run-benchmark --task TaskH_COORD_RISK --coord-method $id --injection $inj --scale $scale --episodes $Episodes --seed $BaseSeed --timing simulated --out "$OutDir/${id}_taskh_${scale}_${inj}.json"
      if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
  }
}

Write-Host "Layer 3 scale done. Output: $OutDir"
