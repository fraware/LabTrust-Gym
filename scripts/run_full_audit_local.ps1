# Full local audit: run all CI-relevant checks (steps 1-6, optional 7) so everything passes before push.
# Mirrors lint-format, no-placeholders, audit-selfcheck, verification battery, release-fixture-verify, coverage.
#
# Usage: .\scripts\run_full_audit_local.ps1
#   Run from repo root. Requires: pip install -e ".[dev,env,docs]"
#
# Env:
#   REPO_ROOT                 repo root (default: parent of script dir)
#   LABTRUST_FULL_AUDIT_WHEEL if 1, also run wheel-smoke simulation (build wheel, fresh venv, audit + validate + quick-eval)
#
# Exit: 0 if all steps pass; 1 on first failure.

$ErrorActionPreference = "Stop"
$RepoRoot = if ($env:REPO_ROOT) { $env:REPO_ROOT } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
Set-Location $RepoRoot

function Run-Step {
    param([string]$Name, [scriptblock]$Block)
    Write-Host "=== $Name ==="
    try {
        & $Block
        if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
            Write-Host "  FAILED (exit $LASTEXITCODE)"
            return $false
        }
        Write-Host "  OK"
        return $true
    } catch {
        Write-Host "  FAILED: $_"
        return $false
    }
}

# Step 1 - Lint and format (fix first, then check)
if (-not (Run-Step "ruff-format-fix" { ruff format . })) { exit 1 }
if (-not (Run-Step "ruff-format-check" { ruff format --check . })) { exit 1 }
if (-not (Run-Step "ruff-check" { ruff check . })) { exit 1 }

# Step 2 - No-placeholders gate
if (-not (Run-Step "no-placeholders" { python tools/no_placeholders.py })) { exit 1 }

# Step 3 - Audit self-check
if (-not (Run-Step "audit-selfcheck" { labtrust audit-selfcheck --out ./audit_self_check })) { exit 1 }

# Step 4 - Full verification battery
if (-not (Run-Step "verification-battery" { & (Join-Path $PSScriptRoot "run_verification_battery.ps1") })) { exit 1 }

# Step 5 - Release fixture verify
if (-not (Run-Step "normalize-release-fixture" { python scripts/normalize_release_fixture_manifests.py })) { exit 1 }
if (-not (Run-Step "release-fixture-verify" { pytest tests/test_release_fixture_verify_release.py -v })) { exit 1 }

# Step 6 - Coverage
if (-not (Run-Step "coverage" { pytest -q -m "not slow" --cov=src/labtrust_gym --cov-report=term --cov-fail-under=54 })) { exit 1 }

# Step 7 - Wheel-smoke simulation (optional)
if ($env:LABTRUST_FULL_AUDIT_WHEEL -eq "1") {
    Write-Host "=== wheel-smoke (optional) ==="
    $distDir = Join-Path $RepoRoot "dist"
    $venvDir = Join-Path $RepoRoot ".venv-wheel-audit"
    if (-not (Test-Path $distDir)) {
        if (-not (Run-Step "wheel-build-deps" { pip install build })) { exit 1 }
        if (-not (Run-Step "wheel-build" { python -m build --wheel --outdir dist . })) { exit 1 }
    }
    if (-not (Test-Path $venvDir)) {
        if (-not (Run-Step "wheel-venv" { python -m venv $venvDir })) { exit 1 }
    }
    $pip = Join-Path $venvDir "Scripts\pip.exe"
    $labtrust = Join-Path $venvDir "Scripts\labtrust.exe"
    $wheel = Get-ChildItem -Path $distDir -Filter "*.whl" | Select-Object -First 1
    if (-not $wheel) {
        Write-Host "  FAILED: no wheel in dist/"
        exit 1
    }
    if (-not (Run-Step "wheel-install" { & $pip install $wheel.FullName })) { exit 1 }
    if (-not (Run-Step "wheel-install-env" { & $pip install ".[env]" })) { exit 1 }
    if (-not (Run-Step "wheel-install-pytest" { & $pip install pytest })) { exit 1 }
    if (-not (Run-Step "wheel-audit-selfcheck" { & $labtrust audit-selfcheck --out ./audit_out })) { exit 1 }
    if (-not (Run-Step "wheel-validate-policy" { & $labtrust validate-policy })) { exit 1 }
    if (-not (Run-Step "wheel-quick-eval" { & $labtrust quick-eval --seed 42 })) { exit 1 }
    Write-Host "  OK"
}

Write-Host "Full local audit passed."
