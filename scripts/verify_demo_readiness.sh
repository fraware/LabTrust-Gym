#!/usr/bin/env bash
# Verify demo readiness for all three presentation tiers (Tier 1/2 full pipeline, Tier 3 compact pack).
# Runs prerequisites check, Tier 3 official pack smoke, and E2E verification chain.
# Optional: set LABTRUST_DEMO_READINESS_FULL_PIPELINE=1 to run a minimal full-pipeline sniff (slower).
#
# Usage: bash scripts/verify_demo_readiness.sh [work_dir]
#   work_dir: optional; default is a new temp directory.
#
# Env:
#   REPO_ROOT                        repo root (default: parent of script dir)
#   SEED_BASE                        seed for package-release and pack (default: 100)
#   LABTRUST_ALLOW_NETWORK           0 (default) for reproducibility
#   LABTRUST_DEMO_READINESS_FULL_PIPELINE  if 1, run minimal full pipeline (hospital_lab, smoke); timeout 20 min
#
# Exit: 0 if all steps pass; non-zero on first failure (stderr and step name printed).
set -eu

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SEED_BASE="${SEED_BASE:-100}"

if [ -n "${1:-}" ]; then
  WORK_DIR="$(cd "$1" && pwd)"
  mkdir -p "$WORK_DIR"
else
  WORK_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t labtrust_demo_readiness)
  trap 'rm -rf "$WORK_DIR"' EXIT
fi

PACK_DIR="$WORK_DIR/pack"
RELEASE_DIR="$WORK_DIR/release"
FULL_DIR="$WORK_DIR/full"
LOG_DIR="$WORK_DIR/logs"
mkdir -p "$LOG_DIR"

export LABTRUST_ALLOW_NETWORK="${LABTRUST_ALLOW_NETWORK:-0}"
cd "$REPO_ROOT"

# Resolve CLI (labtrust on PATH or python -m)
if command -v labtrust >/dev/null 2>&1; then
  LABTRUST_CLI=(labtrust)
elif command -v python >/dev/null 2>&1; then
  LABTRUST_CLI=(python -m labtrust_gym.cli.main)
elif command -v python3 >/dev/null 2>&1; then
  LABTRUST_CLI=(python3 -m labtrust_gym.cli.main)
else
  echo "No labtrust, python, or python3 on PATH. Install the package (e.g. pip install -e \".[dev,env,plots]\")."
  exit 1
fi

run_step() {
  local name="$1"
  shift
  echo "=== $name ==="
  if "$@" > "$LOG_DIR/${name}.log" 2>&1; then
    echo "  OK"
    return 0
  else
    echo "  FAILED (exit $?)"
    echo "--- stdout/stderr ---"
    cat "$LOG_DIR/${name}.log"
    return 1
  fi
}

# 1) Prerequisites: version and validate-policy
if ! run_step labtrust-version "${LABTRUST_CLI[@]}" --version; then
  echo "Demo readiness failed at labtrust --version"
  exit 1
fi
if ! run_step validate-policy "${LABTRUST_CLI[@]}" validate-policy; then
  echo "Demo readiness failed at validate-policy"
  exit 1
fi

# 2) Tier 3 (compact): official pack with smoke
export LABTRUST_OFFICIAL_PACK_SMOKE=1
if [ -n "${LABTRUST_PAPER_SMOKE:-}" ]; then
  unset LABTRUST_PAPER_SMOKE
fi
if ! run_step run-official-pack "${LABTRUST_CLI[@]}" run-official-pack --out "$PACK_DIR" --seed-base "$SEED_BASE"; then
  echo "Demo readiness failed at run-official-pack (Tier 3)"
  exit 1
fi
if [ ! -d "$PACK_DIR/baselines/results" ] || [ ! -d "$PACK_DIR/SECURITY" ] || [ ! -d "$PACK_DIR/SAFETY_CASE" ] || [ ! -f "$PACK_DIR/pack_manifest.json" ] || [ ! -f "$PACK_DIR/PACK_SUMMARY.md" ]; then
  echo "Demo readiness failed: official pack missing required dirs/files (baselines/results, SECURITY, SAFETY_CASE, pack_manifest.json, PACK_SUMMARY.md)"
  exit 1
fi
unset LABTRUST_OFFICIAL_PACK_SMOKE

# 3) E2E verification chain (trustworthiness)
if ! run_step package-release "${LABTRUST_CLI[@]}" package-release --profile minimal --seed-base "$SEED_BASE" --out "$RELEASE_DIR"; then
  echo "Demo readiness failed at package-release"
  exit 1
fi
if ! run_step export-risk-register "${LABTRUST_CLI[@]}" export-risk-register --out "$RELEASE_DIR" --runs "$RELEASE_DIR"; then
  echo "Demo readiness failed at export-risk-register"
  exit 1
fi
if [ ! -f "$RELEASE_DIR/RISK_REGISTER_BUNDLE.v0.1.json" ]; then
  echo "Demo readiness failed: risk register bundle not written"
  exit 1
fi
if ! run_step build-release-manifest "${LABTRUST_CLI[@]}" build-release-manifest --release-dir "$RELEASE_DIR"; then
  echo "Demo readiness failed at build-release-manifest"
  exit 1
fi
# Omit --strict-fingerprints so demo readiness passes on all platforms; CI (ci_e2e_artifacts_chain.sh) uses --strict-fingerprints.
if ! run_step verify-release "${LABTRUST_CLI[@]}" verify-release --release-dir "$RELEASE_DIR"; then
  echo "Demo readiness failed at verify-release"
  exit 1
fi

# 4) Optional: minimal full-pipeline sniff (Tier 2)
if [ "${LABTRUST_DEMO_READINESS_FULL_PIPELINE:-0}" = "1" ]; then
  echo "=== full-pipeline-sniff (Tier 2, timeout 1200s) ==="
  if timeout 1200 python scripts/run_hospital_lab_full_pipeline.py --out "$FULL_DIR" --matrix-preset hospital_lab --security smoke --include-coordination-pack --seed-base "$SEED_BASE" > "$LOG_DIR/full_pipeline_sniff.log" 2>&1; then
    if [ -f "$FULL_DIR/summary/full_pipeline_manifest.json" ] && [ -d "$FULL_DIR/baselines" ] && [ -d "$FULL_DIR/SECURITY" ] && [ -d "$FULL_DIR/coordination_pack" ]; then
      echo "  OK"
    else
      echo "  FAILED: full pipeline manifest or key dirs missing"
      cat "$LOG_DIR/full_pipeline_sniff.log"
      exit 1
    fi
  else
    echo "  FAILED (exit $?)"
    cat "$LOG_DIR/full_pipeline_sniff.log"
    exit 1
  fi
fi

echo "Demo readiness passed (work_dir=$WORK_DIR). All three tiers are ready."

