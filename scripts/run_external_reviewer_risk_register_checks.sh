#!/usr/bin/env bash
# External reviewer risk register checks: run security suite smoke and/or
# coordination study smoke (or use provided dirs), export-risk-register,
# validate schema and crosswalk, optionally verify-bundle on one evidence bundle.
# Exit non-zero on contract/crosswalk failures.
#
# Usage: run_external_reviewer_risk_register_checks.sh [out_dir] [security_dir] [coord_dir]
#   out_dir:      output directory for bundle and, if not provided, generated runs (default: ./risk_register_reviewer_out)
#   security_dir: if set, use for SECURITY evidence; else run security suite smoke into out_dir/security_smoke
#   coord_dir:    if set, use for coordination evidence; else run coordination study into out_dir/coordination_smoke
#
# Env:
#   LABTRUST_STRICT_COVERAGE=1  exit 1 when any required_bench (method, risk) cell has no evidence and is not waived
#   REPO_ROOT                   repo root (default: parent of script dir)
#
# No network, no secrets. Exit 0 only if all checks pass.
set -eu

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
OUT_DIR="${1:-}"
SECURITY_DIR="${2:-}"
COORD_DIR="${3:-}"

if [ -z "$OUT_DIR" ]; then
  OUT_DIR="$REPO_ROOT/risk_register_reviewer_out"
fi
mkdir -p "$OUT_DIR"

cd "$REPO_ROOT"

# Resolve run dirs: use provided or generate smoke runs
RUN_DIRS=()
if [ -n "$SECURITY_DIR" ]; then
  if [ ! -d "$SECURITY_DIR" ]; then
    echo "Security dir not found: $SECURITY_DIR"
    exit 1
  fi
  RUN_DIRS+=("$SECURITY_DIR")
else
  SECURITY_SMOKE="$OUT_DIR/security_smoke"
  mkdir -p "$SECURITY_SMOKE"
  echo "Running security suite smoke..."
  labtrust run-security-suite --out "$SECURITY_SMOKE" --seed 42
  RUN_DIRS+=("$SECURITY_SMOKE")
fi

if [ -n "$COORD_DIR" ]; then
  if [ ! -d "$COORD_DIR" ]; then
    echo "Coordination dir not found: $COORD_DIR"
    exit 1
  fi
  RUN_DIRS+=("$COORD_DIR")
else
  COORD_SPEC="$REPO_ROOT/policy/coordination/coordination_study_spec.v0.1.yaml"
  if [ ! -f "$COORD_SPEC" ]; then
    echo "Coordination spec not found: $COORD_SPEC"
    exit 1
  fi
  COORD_SMOKE="$OUT_DIR/coordination_smoke"
  mkdir -p "$COORD_SMOKE"
  export LABTRUST_REPRO_SMOKE=1
  echo "Running coordination study (deterministic)..."
  labtrust run-coordination-study --spec "$COORD_SPEC" --out "$COORD_SMOKE" --llm-backend deterministic
  if [ ! -f "$COORD_SMOKE/summary/summary_coord.csv" ]; then
    echo "Missing $COORD_SMOKE/summary/summary_coord.csv"
    exit 1
  fi
  RUN_DIRS+=("$COORD_SMOKE")
fi

# Verify run evidence before using for export (bundles + SECURITY checksums)
echo "Verifying run evidence..."
python3 scripts/verify_run_evidence.py --policy-root "$REPO_ROOT" "${RUN_DIRS[@]}" || exit 1

# Export risk register
echo "Exporting risk register..."
ARGS=("--out" "$OUT_DIR")
for d in "${RUN_DIRS[@]}"; do
  ARGS+=("--runs" "$d")
done
labtrust export-risk-register "${ARGS[@]}"

BUNDLE_PATH="$OUT_DIR/RISK_REGISTER_BUNDLE.v0.1.json"
if [ ! -f "$BUNDLE_PATH" ]; then
  echo "Bundle not written: $BUNDLE_PATH"
  exit 1
fi

# Crosswalk integrity on the written bundle
echo "Checking crosswalk integrity..."
export _BUNDLE_PATH="$BUNDLE_PATH" _REPO_ROOT="$REPO_ROOT"
python -c "
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
"
echo "Schema and crosswalk OK."

# Optional: verify-bundle on first EvidenceBundle
BUNDLE_DIR=$(find "$OUT_DIR" -maxdepth 5 -type d -name "EvidenceBundle*" 2>/dev/null | head -n 1)
if [ -z "$BUNDLE_DIR" ]; then
  for d in "${RUN_DIRS[@]}"; do
    BUNDLE_DIR=$(find "$d" -maxdepth 5 -type d -name "EvidenceBundle*" 2>/dev/null | head -n 1)
    [ -n "$BUNDLE_DIR" ] && break
  done
fi
if [ -n "$BUNDLE_DIR" ]; then
  echo "Running verify-bundle on $BUNDLE_DIR..."
  labtrust verify-bundle --bundle "$BUNDLE_DIR" || true
fi

echo "All external reviewer risk register checks passed."
