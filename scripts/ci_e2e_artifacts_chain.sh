#!/usr/bin/env bash
# E2E reproducible artifact chain: package-release (minimal) -> verify-bundle -> export-risk-register.
# Asserts all steps succeed with deterministic inputs and without network.
# Use for CI gate and local "one button" proof (make e2e-artifacts-chain).
#
# Usage: ci_e2e_artifacts_chain.sh [work_dir]
#   work_dir: optional; default is a new temp directory under repo or $TMPDIR.
#
# Env:
#   REPO_ROOT     repo root (default: parent of script dir)
#   SEED_BASE     seed for package-release (default: 100)
#
# Exit: 0 if full chain passes; non-zero if any step fails or risk register has crosswalk/errors.
# No network. Uses repo CLI entrypoints only.
set -eu

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SEED_BASE="${SEED_BASE:-100}"

if [ -n "${1:-}" ]; then
  WORK_DIR="$(cd "$1" && pwd)"
  mkdir -p "$WORK_DIR"
else
  WORK_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t labtrust_e2e)
  trap 'rm -rf "$WORK_DIR"' EXIT
fi

RELEASE_DIR="$WORK_DIR/release"
RISK_OUT_DIR="$WORK_DIR/risk_out"
LOG_DIR="$WORK_DIR/logs"
mkdir -p "$LOG_DIR"

# Ensure no network for reproducibility
export LABTRUST_ALLOW_NETWORK="${LABTRUST_ALLOW_NETWORK:-0}"

cd "$REPO_ROOT"

# Prefer labtrust on PATH (CI); fallback to python -m for portability
if command -v labtrust >/dev/null 2>&1; then
  LABTRUST_CLI=(labtrust)
elif command -v python >/dev/null 2>&1; then
  LABTRUST_CLI=(python -m labtrust_gym.cli.main)
elif command -v python3 >/dev/null 2>&1; then
  LABTRUST_CLI=(python3 -m labtrust_gym.cli.main)
else
  echo "No labtrust, python, or python3 on PATH. Install the package (e.g. pip install -e \".[dev,env,plots]\") and ensure CLI or Python is on PATH."
  exit 1
fi

run_step() {
  local name="$1"
  shift
  echo "=== $name ==="
  if "$@" > "$LOG_DIR/${name}.log" 2>&1; then
    echo "  OK"
    return 0
  else
    echo "  FAILED (exit $?)"
    echo "--- stdout/stderr ---"
    cat "$LOG_DIR/${name}.log"
    return 1
  fi
}

# 1) Package-release minimal (deterministic, no network)
if ! run_step package-release "${LABTRUST_CLI[@]}" package-release --profile minimal --seed-base "$SEED_BASE" --out "$RELEASE_DIR"; then
  echo "E2E chain failed at package-release"
  exit 1
fi

# 1b) Determinism report (throughput_sla, 3 episodes, seed 42)
DET_OUT="$WORK_DIR/det_report"
if ! run_step determinism-report "${LABTRUST_CLI[@]}" determinism-report --task throughput_sla --episodes 3 --seed 42 --out "$DET_OUT"; then
  echo "E2E chain failed at determinism-report"
  exit 1
fi
if [ ! -f "$DET_OUT/determinism_report.json" ] || [ ! -f "$DET_OUT/determinism_report.md" ]; then
  echo "E2E chain failed: determinism-report did not write determinism_report.json and determinism_report.md"
  exit 1
fi

# 2) Verify all EvidenceBundles under the release
if ! run_step verify-release "${LABTRUST_CLI[@]}" verify-release --release-dir "$RELEASE_DIR"; then
  echo "E2E chain failed at verify-release"
  exit 1
fi

# 3) Export risk register from release dir
if ! run_step export-risk-register "${LABTRUST_CLI[@]}" export-risk-register --out "$RISK_OUT_DIR" --runs "$RELEASE_DIR"; then
  echo "E2E chain failed at export-risk-register"
  exit 1
fi

BUNDLE_PATH="$RISK_OUT_DIR/RISK_REGISTER_BUNDLE.v0.1.json"
if [ ! -f "$BUNDLE_PATH" ]; then
  echo "Risk register bundle not written: $BUNDLE_PATH"
  exit 1
fi

# 4) Schema and crosswalk integrity (fail CI on crosswalk errors or missing refs)
echo "=== schema-and-crosswalk ==="
export _BUNDLE_PATH="$BUNDLE_PATH" _REPO_ROOT="$REPO_ROOT"
python -c "
from pathlib import Path
import json
import os
from labtrust_gym.export.risk_register_bundle import (
    check_crosswalk_integrity,
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
print('Schema and crosswalk OK.')
" 2>&1 | tee "$LOG_DIR/schema-and-crosswalk.log"
if [ "${PIPESTATUS[0]}" -ne 0 ]; then
  echo "E2E chain failed at schema/crosswalk"
  exit 1
fi

# 5) Sanity: bundle has evidence or links (references release)
echo "=== bundle-references-release ==="
export _BUNDLE_PATH="$BUNDLE_PATH"
python -c "
import json
import os
from pathlib import Path
bundle_path = Path(os.environ['_BUNDLE_PATH'])
bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
links = bundle.get('links') or []
evidence = bundle.get('evidence') or []
if not evidence and not links:
    print('Bundle has no evidence and no links')
    raise SystemExit(1)
print('Bundle has', len(evidence), 'evidence entries,', len(links), 'links.')
" 2>&1 | tee -a "$LOG_DIR/schema-and-crosswalk.log"
if [ "${PIPESTATUS[0]}" -ne 0 ]; then
  echo "E2E chain failed: bundle missing evidence/links"
  exit 1
fi

echo "E2E artifacts chain passed (release=$RELEASE_DIR, risk_out=$RISK_OUT_DIR)."
