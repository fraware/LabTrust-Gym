#!/usr/bin/env bash
# Forker quickstart: validate-policy, run coordination pack (fixed + critical), build report, export risk register.
# Usage: bash scripts/forker_quickstart.sh [OUT_DIR]
#   OUT_DIR defaults to ./labtrust_runs/forker_quickstart_<timestamp>

set -e
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_ROOT"

OUT="${1:-}"
if [ -z "$OUT" ]; then
  OUT="./labtrust_runs/forker_quickstart_$(date +%Y%m%d_%H%M%S)"
fi

if command -v labtrust >/dev/null 2>&1; then
  LABTRUST=(labtrust)
elif command -v python >/dev/null 2>&1; then
  LABTRUST=(python -m labtrust_gym.cli.main)
else
  echo "Install the package (pip install -e \".[dev,env]\") and ensure labtrust or python is on PATH."
  exit 1
fi

echo "=== Forker quickstart (out=$OUT) ==="
"${LABTRUST[@]}" forker-quickstart --out "$OUT"
echo "Done. COORDINATION_DECISION and risk register under $OUT"
