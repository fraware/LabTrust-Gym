# Layer 2 — Coverage: full method x risk matrix from coordination study spec.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }
Set-Location $RepoRoot

$OutDir = if ($env:OUT_DIR) { $env:OUT_DIR } else { "labtrust_runs/sota_matrix" }
$Spec = if ($env:SPEC) { $env:SPEC } else { "policy/coordination/coordination_study_spec.v0.1.yaml" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
& labtrust run-coordination-study --spec $Spec --out $OutDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Layer 2 coverage done. Output: $OutDir"
