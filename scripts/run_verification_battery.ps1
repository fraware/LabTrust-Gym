# Verification battery: run Phase A checks plus golden, determinism-report,
# risk-register gate, quick-eval, baseline-regression, and docs build.
# Windows/PowerShell equivalent of run_verification_battery.sh.
#
# Usage: .\scripts\run_verification_battery.ps1
#   Run from repo root. Requires: pip install -e ".[dev,env,docs]"
#
# Env:
#   REPO_ROOT          repo root (default: parent of script dir)
#   LABTRUST_BATTERY_E2E  if 1, attempt e2e-artifacts-chain (requires bash/WSL)
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

# 1) Lint/format
if (-not (Run-Step "lint-format" { ruff format --check . })) { exit 1 }
if (-not (Run-Step "ruff-check" { ruff check . })) { exit 1 }

# 2) Typecheck
if (-not (Run-Step "typecheck" { mypy src/ })) { exit 1 }

# 3) No placeholders
if (-not (Run-Step "no-placeholders" { python tools/no_placeholders.py })) { exit 1 }

# 4) Policy validate
if (-not (Run-Step "validate-policy" { labtrust validate-policy })) { exit 1 }
if (-not (Run-Step "validate-policy-partner" { labtrust validate-policy --partner hsl_like })) { exit 1 }

# 5) Verify ui_fixtures bundle
if (-not (Run-Step "verify-bundle" { labtrust verify-bundle --bundle tests/fixtures/ui_fixtures/evidence_bundle/EvidenceBundle.v0.1 })) { exit 1 }

# 6) Risk register gate
if (-not (Run-Step "export-risk-register" { labtrust export-risk-register --out ./risk_register_out --runs tests/fixtures/ui_fixtures })) { exit 1 }
if (-not (Run-Step "risk-register-contract" { pytest tests/test_risk_register_contract_gate.py -v })) { exit 1 }

# 7) Fast tests
if (-not (Run-Step "pytest-fast" { pytest -q -m "not slow" })) { exit 1 }

# 8) Golden suite
$env:LABTRUST_RUN_GOLDEN = "1"
if (-not (Run-Step "golden-suite" { pytest tests/test_golden_suite.py -q })) { exit 1 }

# 9) Determinism report
if (-not (Run-Step "determinism-report" { labtrust determinism-report --task throughput_sla --episodes 3 --seed 42 --out ./det_report })) { exit 1 }
if (-not (Test-Path "./det_report/determinism_report.json")) {
    Write-Host "  FAILED: det_report/determinism_report.json missing"
    exit 1
}
$detOk = python -c "import json; d=json.load(open('det_report/determinism_report.json')); assert d.get('passed') is True, d.get('errors', ['unknown'])"
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host "  determinism passed"

# 10) Quick-eval
if (-not (Run-Step "quick-eval" { labtrust quick-eval --seed 42 --out-dir ./labtrust_runs })) { exit 1 }

# 11) Baseline regression (conditional)
$hasBaselines = Get-ChildItem -Path "benchmarks/baselines_official/v0.2/results" -Filter "*.json" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($hasBaselines) {
    if (-not (Run-Step "baseline-regression" { $env:LABTRUST_CHECK_BASELINES = "1"; pytest tests/test_official_baselines_regression.py -v })) { exit 1 }
} else {
    Write-Host "=== baseline-regression (skip) ==="
    Write-Host "  Skipped: benchmarks/baselines_official/v0.2/results/*.json not found"
}

# 12) Docs
if (-not (Run-Step "docs" { pip install -e ".[docs]" -q; mkdocs build --strict })) { exit 1 }

# 13) Optional E2E artifacts chain
if ($env:LABTRUST_BATTERY_E2E -eq "1") {
    if (Get-Command bash -ErrorAction SilentlyContinue) {
        if (-not (Run-Step "e2e-artifacts-chain" { bash scripts/ci_e2e_artifacts_chain.sh })) { exit 1 }
    } else {
        Write-Host "=== e2e-artifacts-chain (skip) ==="
        Write-Host "  Skipped: bash not found; set LABTRUST_BATTERY_E2E=0 or use WSL"
    }
}

Write-Host "Verification battery passed."
