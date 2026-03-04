# External reviewer risk register checks: run security suite smoke and/or
# coordination study smoke (or use provided dirs), export-risk-register,
# validate schema and crosswalk, optionally verify-bundle on one evidence bundle.
# Exit non-zero on contract/crosswalk failures.
#
# Usage: .\run_external_reviewer_risk_register_checks.ps1 [OutDir] [SecurityDir] [CoordDir]
#   OutDir:      output directory for bundle and, if not provided, generated runs (default: .\risk_register_reviewer_out)
#   SecurityDir: if set, use for SECURITY evidence; else run security suite smoke into OutDir\security_smoke
#   CoordDir:    if set, use for coordination evidence; else run coordination study into OutDir\coordination_smoke
#
# Env: LABTRUST_STRICT_COVERAGE=1 to exit 1 when required_bench cells missing and not waived.
$ErrorActionPreference = "Stop"

$RepoRoot = if ($env:REPO_ROOT) { $env:REPO_ROOT } else { (Get-Item $PSScriptRoot).Parent.FullName }
$OutDir = $args[0]
$SecurityDir = $args[1]
$CoordDir = $args[2]
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "risk_register_reviewer_out" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$RunDirs = @()
if ($SecurityDir) {
    if (-not (Test-Path $SecurityDir -PathType Container)) {
        Write-Error "Security dir not found: $SecurityDir"
        exit 1
    }
    $RunDirs += $SecurityDir
} else {
    $SecuritySmoke = Join-Path $OutDir "security_smoke"
    New-Item -ItemType Directory -Force -Path $SecuritySmoke | Out-Null
    Write-Host "Running security suite smoke..."
    & labtrust run-security-suite --out $SecuritySmoke --seed 42
    $RunDirs += $SecuritySmoke
}

if ($CoordDir) {
    if (-not (Test-Path $CoordDir -PathType Container)) {
        Write-Error "Coordination dir not found: $CoordDir"
        exit 1
    }
    $RunDirs += $CoordDir
} else {
    $CoordSpec = Join-Path $RepoRoot "policy\coordination\coordination_study_spec.v0.1.yaml"
    if (-not (Test-Path $CoordSpec)) {
        Write-Error "Coordination spec not found: $CoordSpec"
        exit 1
    }
    $CoordSmoke = Join-Path $OutDir "coordination_smoke"
    New-Item -ItemType Directory -Force -Path $CoordSmoke | Out-Null
    $env:LABTRUST_REPRO_SMOKE = "1"
    Write-Host "Running coordination study (deterministic)..."
    & labtrust run-coordination-study --spec $CoordSpec --out $CoordSmoke --llm-backend deterministic
    $SummaryCsv = Join-Path $CoordSmoke "summary\summary_coord.csv"
    if (-not (Test-Path $SummaryCsv)) {
        Write-Error "Missing $SummaryCsv"
        exit 1
    }
    $RunDirs += $CoordSmoke
}

Push-Location $RepoRoot
try {
    Write-Host "Verifying run evidence..."
    $VerifyArgs = @("scripts/verify_run_evidence.py", "--policy-root", $RepoRoot) + $RunDirs
    & python @VerifyArgs
    if ($LASTEXITCODE -ne 0) { throw "verify_run_evidence failed" }

    Write-Host "Exporting risk register..."
    $ExportArgs = @("export-risk-register", "--out", $OutDir)
    foreach ($d in $RunDirs) {
        $ExportArgs += "--runs"; $ExportArgs += $d
    }
    & labtrust @ExportArgs

    $BundlePath = Join-Path $OutDir "RISK_REGISTER_BUNDLE.v0.1.json"
    if (-not (Test-Path $BundlePath)) {
        Write-Error "Bundle not written: $BundlePath"
        exit 1
    }

    Write-Host "Checking crosswalk integrity..."
    $env:_BUNDLE_PATH = $BundlePath
    $env:_REPO_ROOT = $RepoRoot
    python -c @"
from pathlib import Path
import json
import os
from labtrust_gym.export.risk_register_bundle import (
    check_crosswalk_integrity,
    check_risk_register_coverage,
    validate_bundle_against_schema,
)
bundle_path = Path(os.environ['_BUNDLE_PATH'])
repo_root = Path(os.environ['_REPO_ROOT'])
bundle = json.loads(bundle_path.read_text(encoding='utf-8'))

errors = validate_bundle_against_schema(bundle, repo_root)
if errors:
    for e in errors:
        print('Schema:', e)
    raise SystemExit(1)

errors = check_crosswalk_integrity(bundle)
if errors:
    for e in errors:
        print('Crosswalk:', e)
    raise SystemExit(1)

strict = os.environ.get('LABTRUST_STRICT_COVERAGE', '') == '1'
if strict:
    passed, missing = check_risk_register_coverage(bundle, repo_root, waived_risk_ids=None)
    if not passed:
        for mid, rid in missing:
            print(f'Coverage missing: method_id={mid!r}, risk_id={rid!r}')
        raise SystemExit(1)
"@
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Schema and crosswalk OK."

    $BundleDir = $null
    foreach ($d in @($OutDir) + $RunDirs) {
        $found = Get-ChildItem -Path $d -Recurse -Directory -Filter "EvidenceBundle*" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $BundleDir = $found.FullName; break }
    }
    if ($BundleDir) {
        Write-Host "Running verify-bundle on $BundleDir..."
        $proc = Start-Process -FilePath "labtrust" -ArgumentList "verify-bundle", "--bundle", $BundleDir -Wait -NoNewWindow -PassThru
        if ($proc.ExitCode -ne 0) { Write-Host "verify-bundle exited $($proc.ExitCode) (optional, ignoring)." }
    }

    Write-Host "All external reviewer risk register checks passed."
} finally {
    Pop-Location
}
