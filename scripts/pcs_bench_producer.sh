#!/usr/bin/env bash
# Release-grade LabTrust reproducibility producer + optional pcs-bench ingest validation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PCS_CORE="${PCS_CORE:-$ROOT/../pcs-core}"
export PCS_BENCH="${PCS_BENCH:-$ROOT/../pcs-bench}"
export BENCH_RUN_DIR="${BENCH_RUN_DIR:-benchmark_runs/labtrust_reproducibility}"
exec python scripts/pcs_bench_producer.py \
  --pcs-core "$PCS_CORE" \
  --pcs-bench "$PCS_BENCH" \
  --out "$BENCH_RUN_DIR" \
  "$@"
