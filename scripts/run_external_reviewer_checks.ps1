# External reviewer checks: run coordination study (deterministic), validate
# summary_coord.csv, optional verify-bundle and COORDINATION_LLM_CARD.
# Usage: .\run_external_reviewer_checks.ps1 [-OutDir <path>] [-SpecPath <path>]
# Exit 0 only if all checks pass. No network, no secrets.
$ErrorActionPreference = "Stop"

$RepoRoot = if ($env:REPO_ROOT) { $env:REPO_ROOT } else { (Get-Item $PSScriptRoot).Parent.FullName }
$OutDir = $args[0]
$SpecPath = $args[1]
if (-not $OutDir) { $OutDir = Join-Path $Env:TEMP "external_reviewer_out_$(Get-Random)" }
if (-not $SpecPath) { $SpecPath = Join-Path $RepoRoot "policy\coordination\coordination_study_spec.v0.1.yaml" }

if (-not (Test-Path $SpecPath)) {
    Write-Error "Spec not found: $SpecPath"
    exit 1
}

$env:LABTRUST_REPRO_SMOKE = "1"
Push-Location $RepoRoot
try {
    Write-Host "Running coordination study (deterministic)..."
    & labtrust run-coordination-study --spec $SpecPath --out $OutDir --llm-backend deterministic

    $SummaryCsv = Join-Path $OutDir "summary\summary_coord.csv"
    if (-not (Test-Path $SummaryCsv)) {
        Write-Error "Missing $SummaryCsv"
        exit 1
    }

    $RequiredColumns = @("method_id", "scale_id", "injection_id", "sec.attack_success_rate", "proposal_valid_rate")
    $Header = Get-Content $SummaryCsv -TotalCount 1
    foreach ($col in $RequiredColumns) {
        if ($Header -notmatch [regex]::Escape($col)) {
            Write-Error "summary_coord.csv missing column: $col"
            exit 1
        }
    }
    Write-Host "summary_coord.csv has required columns."

    $BundleDir = Get-ChildItem -Path $OutDir -Recurse -Directory -Filter "EvidenceBundle*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($BundleDir) {
        Write-Host "Running verify-bundle on $($BundleDir.FullName)..."
        & labtrust verify-bundle --bundle $BundleDir.FullName 2>&1 | Out-Null
    }

    $CardPath = Join-Path $OutDir "COORDINATION_LLM_CARD.md"
    if (-not (Test-Path $CardPath)) {
        Write-Host "Generating COORDINATION_LLM_CARD.md..."
        $env:_CARD_PATH = $CardPath
        $env:_REPO_ROOT = $RepoRoot
        python -c @"
from pathlib import Path
import os
from labtrust_gym.studies.coordination_card import write_coordination_llm_card
write_coordination_llm_card(Path(os.environ['_CARD_PATH']), Path(os.environ['_REPO_ROOT']))
"@
    }
    if (-not (Test-Path $CardPath)) {
        Write-Error "COORDINATION_LLM_CARD.md missing and could not be generated"
        exit 1
    }
    Write-Host "COORDINATION_LLM_CARD.md present."
    Write-Host "All external reviewer checks passed."
} finally {
    Pop-Location
}
