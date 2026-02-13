#!/usr/bin/env bash
# Layer 1 - Sanity: TaskG (S scale, 3 seeds) + TaskH (S scale, 1 injection, 3 seeds)
# for SOTA methods + baselines (market_auction, kernel_whca).
# Override methods via space-separated LABTRUST_SANITY_METHODS (default below).
# Set LABTRUST_SANITY_FULL=1 to run TaskG + TaskH(none) for every method_id from
# policy/coordination/coordination_methods.v0.1.yaml (excludes marl_ppo).

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="${OUT_DIR:-labtrust_runs/sota_sanity}"
TASKG_SEED="${TASKG_SEED:-100}"
TASKH_SEED="${TASKH_SEED:-200}"
INJECTION="${INJECTION:-INJ-COMMS-POISON-001}"

if [ "${LABTRUST_SANITY_FULL:-0}" = "1" ]; then
  METHODS="$(python -c "
from pathlib import Path
from labtrust_gym.policy.coordination import load_coordination_methods
p = Path('policy/coordination/coordination_methods.v0.1.yaml')
reg = load_coordination_methods(p)
# Exclude marl_ppo (optional SB3); LLM methods run with --llm-backend deterministic
ids = [m for m in sorted(reg.keys()) if m != 'marl_ppo']
print(' '.join(ids))
")"
else
  METHODS="${LABTRUST_SANITY_METHODS:-kernel_whca market_auction ripple_effect group_evolving_experience_sharing}"
fi

mkdir -p "$OUT_DIR"

for id in $METHODS; do
  echo "Layer1 sanity: $id coord_scale..."
  labtrust run-benchmark --task coord_scale --coord-method "$id" --scale small_smoke --episodes 3 --seed "$TASKG_SEED" --out "$OUT_DIR/${id}_taskg.json" --llm-backend deterministic || exit 1
  echo "Layer1 sanity: $id coord_risk $INJECTION..."
  labtrust run-benchmark --task coord_risk --coord-method "$id" --injection "$INJECTION" --scale small_smoke --episodes 3 --seed "$TASKH_SEED" --out "$OUT_DIR/${id}_taskh_poison.json" --llm-backend deterministic || exit 1
  if [ "${LABTRUST_SANITY_FULL:-0}" = "1" ]; then
    echo "Layer1 sanity: $id coord_risk baseline (none)..."
    labtrust run-benchmark --task coord_risk --coord-method "$id" --scale small_smoke --episodes 1 --seed "$TASKH_SEED" --out "$OUT_DIR/${id}_taskh_none.json" --llm-backend deterministic || exit 1
  fi
done

echo "Layer 1 sanity done. Output: $OUT_DIR"
