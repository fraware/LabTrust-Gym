#!/usr/bin/env bash
# Quickstart: install, validate-policy, quick-eval, paper artifact, verify-bundle.
# Run from repo root. For v0.1.0 release reproducibility.
# Usage: bash scripts/quickstart_paper_v0_1.sh

set -e
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_ROOT"

echo "=== 1. Install ==="
pip install -e ".[dev,env,plots]" --quiet
labtrust --version

echo "=== 2. Validate policy ==="
labtrust validate-policy

echo "=== 3. Quick-eval (TaskA, TaskD, TaskE) ==="
labtrust quick-eval --seed 42

echo "=== 4. Paper artifact (paper_v0.1) ==="
OUT="${OUT:-./labtrust_paper_v0.1}"
labtrust package-release --profile paper_v0.1 --seed-base 100 --out "$OUT"

echo "=== 5. Verify evidence bundle ==="
BUNDLE_DIR=$(find "$OUT" -type d -name "EvidenceBundle.v0.1" 2>/dev/null | head -1)
if [ -n "$BUNDLE_DIR" ] && [ -d "$BUNDLE_DIR" ]; then
  labtrust verify-bundle --bundle "$BUNDLE_DIR"
  echo "Verify-bundle passed."
else
  echo "No EvidenceBundle.v0.1 dir found under $OUT; skip verify-bundle."
fi

echo "=== Quickstart done ==="
