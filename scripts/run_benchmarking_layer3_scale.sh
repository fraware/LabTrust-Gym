#!/usr/bin/env bash
# Layer 3 - Scale: TaskG and TaskH at S/M/L; TaskH with top 3 injections;
# 10-30 episodes per cell; timing_mode=simulated.
# Override: LABTRUST_SCALE_METHODS, LABTRUST_SCALE_INJECTIONS, EPISODES, OUT_DIR.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="${OUT_DIR:-labtrust_runs/sota_scale}"
# S=small_smoke, M=medium_stress_signed_bus, L=corridor_heavy
SCALES="${LABTRUST_SCALE_SCALES:-small_smoke medium_stress_signed_bus corridor_heavy}"
METHODS="${LABTRUST_SCALE_METHODS:-kernel_whca market_auction ripple_effect group_evolving_experience_sharing}"
# Top 3 injections for TaskH
INJECTIONS="${LABTRUST_SCALE_INJECTIONS:-INJ-COMMS-POISON-001 INJ-ID-SPOOF-001 INJ-COLLUSION-001}"
EPISODES="${EPISODES:-15}"
BASE_SEED="${BASE_SEED:-300}"

mkdir -p "$OUT_DIR"

for id in $METHODS; do
  for scale in $SCALES; do
    echo "Layer3 scale: $id TaskG scale=$scale..."
    labtrust run-benchmark --task TaskG_COORD_SCALE --coord-method "$id" --scale "$scale" --episodes "$EPISODES" --seed "$BASE_SEED" --timing simulated --out "$OUT_DIR/${id}_taskg_${scale}.json" || exit 1
  done
  for scale in $SCALES; do
    for inj in $INJECTIONS; do
      echo "Layer3 scale: $id TaskH scale=$scale injection=$inj..."
      labtrust run-benchmark --task TaskH_COORD_RISK --coord-method "$id" --injection "$inj" --scale "$scale" --episodes "$EPISODES" --seed "$BASE_SEED" --timing simulated --out "$OUT_DIR/${id}_taskh_${scale}_${inj}.json" || exit 1
    done
  done
done

echo "Layer 3 scale done. Output: $OUT_DIR"
