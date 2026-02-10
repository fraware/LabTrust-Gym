#!/usr/bin/env bash
# External reviewer checks: run coordination study (deterministic), validate
# summary_coord.csv, optional verify-bundle and COORDINATION_LLM_CARD.
# Usage: run_external_reviewer_checks.sh [out_dir] [spec_path]
#   out_dir: output directory (default: mktemp -d)
#   spec_path: study spec YAML (default: policy/coordination/coordination_study_spec.v0.1.yaml)
# Exit 0 only if all checks pass. No network, no secrets.
set -eu

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
OUT_DIR="${1:-}"
SPEC_PATH="${2:-}"
if [ -z "$OUT_DIR" ]; then
  OUT_DIR=$(mktemp -d 2>/dev/null || echo "./external_reviewer_out")
fi
if [ -z "$SPEC_PATH" ]; then
  SPEC_PATH="$REPO_ROOT/policy/coordination/coordination_study_spec.v0.1.yaml"
fi
if [ ! -f "$SPEC_PATH" ]; then
  echo "Spec not found: $SPEC_PATH"
  exit 1
fi

cd "$REPO_ROOT"
export LABTRUST_REPRO_SMOKE=1

echo "Running coordination study (deterministic)..."
labtrust run-coordination-study --spec "$SPEC_PATH" --out "$OUT_DIR" --llm-backend deterministic

SUMMARY_CSV="$OUT_DIR/summary/summary_coord.csv"
if [ ! -f "$SUMMARY_CSV" ]; then
  echo "Missing $SUMMARY_CSV"
  exit 1
fi

REQUIRED_COLUMNS="method_id scale_id injection_id sec.attack_success_rate proposal_valid_rate"
HEADER=$(head -n 1 "$SUMMARY_CSV")
for col in $REQUIRED_COLUMNS; do
  if ! echo "$HEADER" | grep -q "$col"; then
    echo "summary_coord.csv missing column: $col"
    exit 1
  fi
done
echo "summary_coord.csv has required columns."

# Coverage gate: every required_bench (method_id, risk_id) must have at least one row
# LABTRUST_STRICT_COVERAGE=1: exit 1 when any required cell is missing; else report missing and continue
MATRIX_PATH="$REPO_ROOT/policy/coordination/method_risk_matrix.v0.1.yaml"
export SUMMARY_CSV MATRIX_PATH
python -c "
from pathlib import Path
import os
from labtrust_gym.studies.coverage_gate import check_summary_coverage
summary_csv = Path(os.environ['SUMMARY_CSV'])
matrix_path = Path(os.environ['MATRIX_PATH'])
strict = os.environ.get('LABTRUST_STRICT_COVERAGE', '') == '1'
check_summary_coverage(summary_csv, matrix_path, strict=strict)
"
echo "Coverage gate: required_bench cells checked."

# Coordination matrix: build from run dir, validate schema, confirm pipeline_mode is llm_live; fail loudly if missing
MATRIX_JSON="$OUT_DIR/coordination_matrix.v0.1.json"
if ! labtrust build-coordination-matrix --run "$OUT_DIR" --out "$OUT_DIR" 2>&1; then
  echo "ERROR: Coordination matrix build failed (matrix is llm_live-only). To include matrix: labtrust run-coordination-study --spec <spec> --out <out> --llm-backend openai_live --emit-coordination-matrix"
  exit 1
fi
if [ ! -f "$MATRIX_JSON" ]; then
  echo "ERROR: Coordination matrix not found at $MATRIX_JSON after build"
  exit 1
fi
python -c "
import json
import sys
from pathlib import Path
matrix_path = Path('$MATRIX_JSON'.replace('\"', ''))
data = json.loads(matrix_path.read_text(encoding='utf-8'))
if data.get('spec', {}).get('scope', {}).get('pipeline_mode') != 'llm_live':
    print('ERROR: Matrix spec.scope.pipeline_mode is not llm_live', file=sys.stderr)
    sys.exit(1)
repo_root = Path('$REPO_ROOT'.replace('\"', ''))
schema_path = repo_root / 'policy' / 'schemas' / 'coordination_matrix.v0.1.schema.json'
if schema_path.exists():
    from labtrust_gym.policy.loader import load_json, validate_against_schema
    schema = load_json(schema_path)
    validate_against_schema(data, schema, matrix_path)
print('Matrix schema valid, pipeline_mode=llm_live.')
"
echo "Coordination matrix: schema valid, pipeline_mode=llm_live."

# Optional: verify-bundle on first EvidenceBundle under out_dir
BUNDLE_DIR=$(find "$OUT_DIR" -maxdepth 4 -type d -name "EvidenceBundle*" 2>/dev/null | head -n 1)
if [ -n "$BUNDLE_DIR" ]; then
  echo "Running verify-bundle on $BUNDLE_DIR..."
  labtrust verify-bundle --bundle "$BUNDLE_DIR" || true
fi

# COORDINATION_LLM_CARD: generate if missing
CARD_PATH="$OUT_DIR/COORDINATION_LLM_CARD.md"
if [ ! -f "$CARD_PATH" ]; then
  echo "Generating COORDINATION_LLM_CARD.md..."
  export _CARD_PATH="$CARD_PATH" _REPO_ROOT="$REPO_ROOT"
  python -c "
from pathlib import Path
import os
from labtrust_gym.studies.coordination_card import write_coordination_llm_card
write_coordination_llm_card(Path(os.environ['_CARD_PATH']), Path(os.environ['_REPO_ROOT']))
"
fi
if [ ! -f "$CARD_PATH" ]; then
  echo "COORDINATION_LLM_CARD.md missing and could not be generated"
  exit 1
fi
echo "COORDINATION_LLM_CARD.md present."

echo "All external reviewer checks passed."
