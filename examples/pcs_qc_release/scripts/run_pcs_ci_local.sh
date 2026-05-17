#!/usr/bin/env bash
# Full PCS CI parity locally: pytest tests/pcs + deterministic export validation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PCS_DETERMINISTIC=1

PYTHON="${PYTHON:-python}"
if [ -x "$ROOT/.venv-pcs/bin/python" ]; then
  PYTHON="$ROOT/.venv-pcs/bin/python"
fi

"$PYTHON" -m pytest tests/pcs -q
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py
echo "PCS local CI OK"
