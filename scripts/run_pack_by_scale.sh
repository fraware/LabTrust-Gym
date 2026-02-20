#!/usr/bin/env bash
# Run the coordination security pack one scale at a time to reduce runtime per job.
# Each scale writes to its own output directory.
#
# Usage (run one scale):
#   ./scripts/run_pack_by_scale.sh small_smoke
#   ./scripts/run_pack_by_scale.sh medium_stress_signed_bus
#   ./scripts/run_pack_by_scale.sh corridor_heavy
#
# Usage (run all three scales in sequence):
#   ./scripts/run_pack_by_scale.sh all
#
# Optional: OUT_BASE, WORKERS, SEED
#   OUT_BASE=pack_run ./scripts/run_pack_by_scale.sh small_smoke
#   WORKERS=8 SEED=42 ./scripts/run_pack_by_scale.sh medium_stress_signed_bus
#
# To build the risk register from all three scale runs:
#   labtrust export-risk-register --out risk_register_out \
#     --runs pack_run_full_matrix/small_smoke \
#     --runs pack_run_full_matrix/medium_stress_signed_bus \
#     --runs pack_run_full_matrix/corridor_heavy

set -euo pipefail
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
OUT_BASE="${OUT_BASE:-$REPO_ROOT/pack_run_full_matrix}"
WORKERS="${WORKERS:-8}"
SEED="${SEED:-42}"

run_one_scale() {
  local scale_id="$1"
  local out_dir="$OUT_BASE/$scale_id"
  echo "Running pack for scale: $scale_id (out: $out_dir, workers: $WORKERS)"
  (cd "$REPO_ROOT" && python -m labtrust_gym.cli.main run-coordination-security-pack \
    --out "$out_dir" \
    --matrix-preset full_matrix \
    --scale-ids "$scale_id" \
    --seed "$SEED" \
    --workers "$WORKERS")
  echo "Done: $scale_id"
}

if [ $# -eq 0 ]; then
  echo "Usage:"
  echo "  Run one scale:  $0 small_smoke | medium_stress_signed_bus | corridor_heavy"
  echo "  Run all three:  $0 all"
  echo ""
  echo "Equivalent labtrust commands (run from repo root):"
  echo "  # small_smoke (4 agents, fastest)"
  echo "  labtrust run-coordination-security-pack --out $OUT_BASE/small_smoke --matrix-preset full_matrix --scale-ids small_smoke --seed $SEED --workers $WORKERS"
  echo "  # medium_stress_signed_bus (75 agents)"
  echo "  labtrust run-coordination-security-pack --out $OUT_BASE/medium_stress_signed_bus --matrix-preset full_matrix --scale-ids medium_stress_signed_bus --seed $SEED --workers $WORKERS"
  echo "  # corridor_heavy (200 agents)"
  echo "  labtrust run-coordination-security-pack --out $OUT_BASE/corridor_heavy --matrix-preset full_matrix --scale-ids corridor_heavy --seed $SEED --workers $WORKERS"
  exit 0
fi

if [ "$1" = "all" ]; then
  run_one_scale small_smoke
  run_one_scale medium_stress_signed_bus
  run_one_scale corridor_heavy
  echo "All three scales finished. Outputs under $OUT_BASE"
  exit 0
fi

case "$1" in
  small_smoke|medium_stress_signed_bus|corridor_heavy)
    run_one_scale "$1"
    ;;
  *)
    echo "Unknown scale: $1. Use small_smoke, medium_stress_signed_bus, corridor_heavy, or all."
    exit 1
    ;;
esac
