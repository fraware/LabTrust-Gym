#!/usr/bin/env bash
# Layer 2 — Coverage: full method x risk matrix from coordination study spec.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="${OUT_DIR:-labtrust_runs/sota_matrix}"
SPEC="${SPEC:-policy/coordination/coordination_study_spec.v0.1.yaml}"

mkdir -p "$OUT_DIR"
labtrust run-coordination-study --spec "$SPEC" --out "$OUT_DIR"
echo "Layer 2 coverage done. Output: $OUT_DIR"
