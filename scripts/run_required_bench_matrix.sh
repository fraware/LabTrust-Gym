#!/usr/bin/env bash
# Required-bench coverage pack (plan-driven): enumerate required cells from method_risk_matrix,
# join with required_bench_plan.v0.1.yaml, run minimal distinct runs, then export-risk-register
# and validate-coverage --strict.
#
# Usage: ./scripts/run_required_bench_matrix.sh [--out DIR]
#   --out DIR  output directory (default: runs/required_bench_pack)
#
# Env: REPO_ROOT, SEED_BASE (default 42), LABTRUST_STRICT_COVERAGE=1 to fail on missing evidence.
# Exit: 0 if validate-coverage --strict passes; 1 if plan incomplete or validate-coverage fails.
set -eu

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
OUT_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done
if [ -z "$OUT_DIR" ]; then
  OUT_DIR="$REPO_ROOT/runs/required_bench_pack"
fi
mkdir -p "$OUT_DIR"
cd "$REPO_ROOT"

SEED_BASE="${SEED_BASE:-42}"
export LABTRUST_ALLOW_NETWORK="${LABTRUST_ALLOW_NETWORK:-0}"

if command -v labtrust >/dev/null 2>&1; then
  LABTRUST=(labtrust)
else
  LABTRUST=(python3 -m labtrust_gym.cli.main)
fi

# Enumerate distinct runs from plan; exit 1 if any required cell has no plan entry
RUNS_LIST="$OUT_DIR/.plan_runs.txt"
python3 scripts/required_bench_plan_runs.py > "$RUNS_LIST" || exit 1

RUN_DIRS=()
while IFS= read -r line; do
  [ -z "$line" ] && continue
  if [ "$line" = "security_suite" ]; then
    SECURITY_DIR="$OUT_DIR/security_smoke"
    mkdir -p "$SECURITY_DIR"
    echo "=== run: security_suite ==="
    "${LABTRUST[@]}" run-security-suite --out "$SECURITY_DIR" --seed "$SEED_BASE"
    RUN_DIRS+=("$SECURITY_DIR")
    continue
  fi
  # coord_risk method_id injection_id suffix
  set -- $line
  kind="$1"
  method_id="$2"
  injection_id="$3"
  suffix="$4"
  [ -z "$suffix" ] && suffix="${method_id}_${injection_id}"
  run_dir="$OUT_DIR/coord_${suffix}"
  mkdir -p "$run_dir"
  echo "=== run: coord_risk $method_id $injection_id ==="
  "${LABTRUST[@]}" run-benchmark --task coord_risk --coord-method "$method_id" \
    --injection "$injection_id" --scale small_smoke --episodes 1 --seed "$SEED_BASE" \
    --out "$run_dir"
  RUN_DIRS+=("$run_dir")
done < "$RUNS_LIST"

# Verify evidence before using: EvidenceBundles under receipts/ and SECURITY/attack_results.json.sha256
if [ ${#RUN_DIRS[@]} -gt 0 ]; then
  echo "=== verify run evidence (bundles + SECURITY checksum) ==="
  python3 scripts/verify_run_evidence.py --policy-root "$REPO_ROOT" "${RUN_DIRS[@]}" || exit 1
fi

# Build --runs args for export-risk-register
RUNS_ARGS=()
for d in "${RUN_DIRS[@]}"; do
  RUNS_ARGS+=(--runs "$d")
done

echo "=== export-risk-register + validate-coverage --strict ==="
if [ ${#RUNS_ARGS[@]} -eq 0 ]; then
  echo "No run dirs from plan (empty plan?). Running security smoke + coord pack fallback."
  SECURITY_DIR="$OUT_DIR/security_smoke"
  COORD_DIR="$OUT_DIR/coord_pack"
  mkdir -p "$SECURITY_DIR" "$COORD_DIR"
  "${LABTRUST[@]}" run-security-suite --out "$SECURITY_DIR" --seed "$SEED_BASE"
  "${LABTRUST[@]}" run-coordination-security-pack --out "$COORD_DIR" --seed "$SEED_BASE" --methods-from fixed --injections-from critical
  echo "=== verify run evidence (bundles + SECURITY checksum) ==="
  python3 scripts/verify_run_evidence.py --policy-root "$REPO_ROOT" "$SECURITY_DIR" "$COORD_DIR" || exit 1
  "${LABTRUST[@]}" export-risk-register --out "$OUT_DIR" --runs "$SECURITY_DIR" --runs "$COORD_DIR"
else
  "${LABTRUST[@]}" export-risk-register --out "$OUT_DIR" "${RUNS_ARGS[@]}"
fi

BUNDLE="$OUT_DIR/RISK_REGISTER_BUNDLE.v0.1.json"
if [ ! -f "$BUNDLE" ]; then
  echo "Bundle not written: $BUNDLE"
  exit 1
fi

"${LABTRUST[@]}" validate-coverage --strict --bundle "$BUNDLE" --out "$OUT_DIR"
echo "Required-bench coverage pack written to $OUT_DIR. validate-coverage --strict passed."
