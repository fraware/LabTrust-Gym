#!/usr/bin/env bash
# CI: deterministic PCS export + pcs-core validation (implementation: ci_validate_pcs_exports.py).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PCS_DETERMINISTIC=1
exec python examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py
