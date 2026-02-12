#!/usr/bin/env bash
# Create a zip of the canonical baseline for publishing (e.g. Zenodo).
# Usage: ./scripts/publish_baseline_artifact.sh [OUTPUT_ZIP]
# Default: labtrust_baselines_v0.2_<YYYYMMDD>.zip in repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASELINE_DIR="benchmarks/baselines_official/v0.2"
if [ ! -d "$BASELINE_DIR" ]; then
  echo "Missing $BASELINE_DIR. Run: labtrust generate-official-baselines --out $BASELINE_DIR --episodes 3 --seed 123 --force"
  exit 1
fi

DATE="${1:-$(date +%Y%m%d)}"
if [[ "$DATE" == *.zip ]]; then
  OUT_ZIP="$DATE"
else
  OUT_ZIP="labtrust_baselines_v0.2_${DATE}.zip"
fi

echo "Creating $OUT_ZIP from $BASELINE_DIR..."
(cd "$(dirname "$BASELINE_DIR")" && zip -r "$REPO_ROOT/$OUT_ZIP" "$(basename "$BASELINE_DIR")")
echo "Done: $OUT_ZIP"
echo "To publish: upload to Zenodo or similar; cite this repo and the regenerate command in README.md inside the zip."
