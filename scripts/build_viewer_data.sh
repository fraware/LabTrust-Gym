#!/usr/bin/env bash
# Build viewer data: export-risk-register from fixtures (or given run dir), write bundle
# to viewer/data/ so the viewer can load it. One-command rebuild for local/dev.
#
# Usage: build_viewer_data.sh [runs_dir]
#   runs_dir: run directory or glob for evidence (default: tests/fixtures/ui_fixtures)
#
# Env: REPO_ROOT (default: parent of script dir)
set -eu

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
RUNS_SPEC="${1:-tests/fixtures/ui_fixtures}"
VIEWER_DATA="$REPO_ROOT/viewer/data"

cd "$REPO_ROOT"
mkdir -p "$VIEWER_DATA"

echo "Exporting risk register (runs: $RUNS_SPEC)..."
labtrust export-risk-register --out "$VIEWER_DATA" --runs "$RUNS_SPEC"

BUNDLE="$VIEWER_DATA/RISK_REGISTER_BUNDLE.v0.1.json"
if [ ! -f "$BUNDLE" ]; then
  echo "Bundle not written: $BUNDLE"
  exit 1
fi

echo "Validating bundle against schema..."
python -c "
from pathlib import Path
import json
from labtrust_gym.export.risk_register_bundle import validate_bundle_against_schema
repo = Path('$REPO_ROOT')
bundle = json.loads(Path('$BUNDLE').read_text(encoding='utf-8'))
errors = validate_bundle_against_schema(bundle, repo)
if errors:
    for e in errors:
        print('Schema:', e)
    raise SystemExit(1)
"
echo "Viewer data built at $VIEWER_DATA"
