#!/usr/bin/env bash
# LabTrust-only PCS QC-release smoke (requires pcs-core on PATH: pip install -e pcs-core/python).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PCS_DETERMINISTIC=1

RUN_DIR="${RUN_DIR:-runs/qc-release}"
TRACE_OUT="${TRACE_OUT:-trace.json}"
RECEIPT_OUT="${RECEIPT_OUT:-runtime_receipt.json}"
BUNDLE_OUT="${BUNDLE_OUT:-science_claim_bundle.pending.json}"

labtrust run-demo qc-release --deterministic --out "$RUN_DIR"
labtrust run-demo qc-release-invalid-missing-qc --deterministic
labtrust run-demo qc-release-invalid-unauthorized --deterministic

labtrust export-trace --run "$RUN_DIR" --out "$TRACE_OUT"
labtrust export-runtime-receipt --run "$RUN_DIR" --out "$RECEIPT_OUT"
labtrust export-pcs --run "$RUN_DIR" --out "$BUNDLE_OUT"

pcs validate "$RECEIPT_OUT"
pcs validate "$BUNDLE_OUT"

python -m pytest tests/pcs/test_golden_deterministic.py::test_golden_artifacts_match_deterministic_generation -q

echo "LabTrust-only PCS smoke OK (run=$RUN_DIR)"
