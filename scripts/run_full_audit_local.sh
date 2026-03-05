#!/usr/bin/env bash
# Full local audit: run all CI-relevant checks (steps 1-6, optional 7) so everything passes before push.
# Mirrors lint-format, no-placeholders, audit-selfcheck, verification battery, release-fixture-verify, coverage.
#
# Usage: bash scripts/run_full_audit_local.sh
#   Run from repo root. Requires: pip install -e ".[dev,env,docs]"
#
# Env:
#   REPO_ROOT                 repo root (default: parent of script dir)
#   LABTRUST_FULL_AUDIT_WHEEL if 1, also run wheel-smoke simulation (build wheel, fresh venv, audit + validate + quick-eval)
#
# Exit: 0 if all steps pass; 1 on first failure.
set -eu

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

run_step() {
  local name="$1"
  shift
  echo "=== $name ==="
  if "$@"; then
    echo "  OK"
    return 0
  else
    echo "  FAILED (exit $?)"
    return 1
  fi
}

# Step 1 - Lint and format (fix first, then check)
run_step "ruff-format-fix" ruff format . || exit 1
run_step "ruff-format-check" ruff format --check . || exit 1
run_step "ruff-check" ruff check . || exit 1

# Step 2 - No-placeholders gate
run_step "no-placeholders" python tools/no_placeholders.py || exit 1

# Step 3 - Audit self-check
run_step "audit-selfcheck" labtrust audit-selfcheck --out ./audit_self_check || exit 1

# Step 4 - Full verification battery
run_step "verification-battery" bash "$SCRIPT_DIR/run_verification_battery.sh" || exit 1

# Step 5 - Release fixture verify
run_step "normalize-release-fixture" python scripts/normalize_release_fixture_manifests.py || exit 1
run_step "release-fixture-verify" pytest tests/test_release_fixture_verify_release.py -v || exit 1

# Step 6 - Coverage
run_step "coverage" pytest -q -m "not slow" --cov=src/labtrust_gym --cov-report=term --cov-fail-under=54 || exit 1

# Step 7 - Wheel-smoke simulation (optional)
if [ "${LABTRUST_FULL_AUDIT_WHEEL:-0}" = "1" ]; then
  echo "=== wheel-smoke (optional) ==="
  if [ ! -d "dist" ] || [ -z "$(find dist -maxdepth 1 -name '*.whl' 2>/dev/null | head -1)" ]; then
    run_step "wheel-build-deps" pip install build || exit 1
    run_step "wheel-build" python -m build --wheel --outdir dist . || exit 1
  fi
  VENV_DIR="$REPO_ROOT/.venv-wheel-audit"
  if [ ! -d "$VENV_DIR" ]; then
    run_step "wheel-venv" python -m venv "$VENV_DIR" || exit 1
  fi
  PIP="$VENV_DIR/bin/pip"
  LABTRUST="$VENV_DIR/bin/labtrust"
  WHEEL="$(find dist -maxdepth 1 -name '*.whl' 2>/dev/null | head -1)"
  if [ -z "$WHEEL" ]; then
    echo "  FAILED: no wheel in dist/"
    exit 1
  fi
  run_step "wheel-install" "$PIP" install "$WHEEL" || exit 1
  run_step "wheel-install-env" "$PIP" install ".[env]" || exit 1
  run_step "wheel-install-pytest" "$PIP" install pytest || exit 1
  run_step "wheel-audit-selfcheck" "$LABTRUST" audit-selfcheck --out ./audit_out || exit 1
  run_step "wheel-validate-policy" "$LABTRUST" validate-policy || exit 1
  run_step "wheel-quick-eval" "$LABTRUST" quick-eval --seed 42 || exit 1
  echo "  OK"
fi

echo "Full local audit passed."
