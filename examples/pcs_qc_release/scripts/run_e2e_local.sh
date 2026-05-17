#!/usr/bin/env bash
# PCS QC-release local end-to-end smoke (LabTrust-Gym only; CertifyEdge/PF/SM in RUNBOOK.md)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PCS_DETERMINISTIC=1
RUN_DIR="${RUN_DIR:-runs/qc-release}"
rm -rf "$RUN_DIR"
labtrust run-demo qc-release --deterministic --out "$RUN_DIR"
labtrust export-trace --run "$RUN_DIR" --out "$RUN_DIR/trace.export.json"
labtrust export-runtime-receipt --run "$RUN_DIR" --out "$RUN_DIR/runtime_receipt.json"
labtrust export-pcs --run "$RUN_DIR" --out "$RUN_DIR/science_claim_bundle.pending.json"
python -m pytest tests/pcs -q
echo "PCS local e2e OK: $RUN_DIR"
