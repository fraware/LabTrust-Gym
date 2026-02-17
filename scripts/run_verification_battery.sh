#!/usr/bin/env bash
# Verification battery: run all Phase A checks plus golden, determinism-report,
# risk-register gate, quick-eval, baseline-regression, and docs build.
# Use for local "run everything" and to mirror CI checks.
#
# Usage: run_verification_battery.sh
#   Run from repo root. Requires: pip install -e ".[dev,env,docs]"
#
# Env:
#   REPO_ROOT          repo root (default: parent of script dir)
#   LABTRUST_BATTERY_E2E  if 1, also run e2e-artifacts-chain at the end (slower)
#
# Exit: 0 if all steps pass; 1 on first failure. Step 11 (baseline regression)
#   skips if benchmarks/baselines_official/v0.2/results/*.json do not exist.
set -eu

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_ROOT"

run_step() {
  local name="$1"
  shift
  echo "=== $name ==="
  if "$@" ; then
    echo "  OK"
    return 0
  else
    echo "  FAILED (exit $?)"
    return 1
  fi
}

# 1) Lint/format
run_step "lint-format" ruff format --check . && run_step "ruff-check" ruff check . || exit 1

# 2) Typecheck
run_step "typecheck" mypy src/ || exit 1

# 3) No placeholders
run_step "no-placeholders" python tools/no_placeholders.py || exit 1

# 4) Policy validate
run_step "validate-policy" labtrust validate-policy || exit 1
run_step "validate-policy-partner" labtrust validate-policy --partner hsl_like || exit 1

# 5) Verify ui_fixtures bundle
run_step "verify-bundle" labtrust verify-bundle --bundle tests/fixtures/ui_fixtures/evidence_bundle/EvidenceBundle.v0.1 || exit 1

# 6) Risk register gate
run_step "export-risk-register" labtrust export-risk-register --out ./risk_register_out --runs tests/fixtures/ui_fixtures || exit 1
run_step "risk-register-contract" pytest tests/test_risk_register_contract_gate.py -v || exit 1

# 7) Fast tests
run_step "pytest-fast" pytest -q -m "not slow" || exit 1

# 8) Golden suite
export LABTRUST_RUN_GOLDEN=1
run_step "golden-suite" pytest tests/test_golden_suite.py -q || exit 1

# 9) Determinism report
run_step "determinism-report" labtrust determinism-report --task throughput_sla --episodes 3 --seed 42 --out ./det_report || exit 1
if [ ! -f "./det_report/determinism_report.json" ]; then
  echo "  FAILED: det_report/determinism_report.json missing"
  exit 1
fi
python -c "import json; d=json.load(open('det_report/determinism_report.json')); assert d.get('passed') is True, d.get('errors', ['unknown'])" || exit 1
echo "  determinism passed"

# 10) Quick-eval
run_step "quick-eval" labtrust quick-eval --seed 42 --out-dir ./labtrust_runs || exit 1

# 11) Baseline regression (conditional)
if find benchmarks/baselines_official/v0.2/results -maxdepth 1 -name "*.json" 2>/dev/null | head -1 | grep -q .; then
  run_step "baseline-regression" env LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v || exit 1
else
  echo "=== baseline-regression (skip) ==="
  echo "  Skipped: benchmarks/baselines_official/v0.2/results/*.json not found"
fi

# 12) Docs
run_step "docs" pip install -e ".[docs]" -q && mkdocs build --strict || exit 1

# 13) Optional E2E artifacts chain
if [ "${LABTRUST_BATTERY_E2E:-0}" = "1" ]; then
  run_step "e2e-artifacts-chain" bash scripts/ci_e2e_artifacts_chain.sh || exit 1
fi

echo "Verification battery passed."
