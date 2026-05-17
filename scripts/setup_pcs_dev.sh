#!/usr/bin/env bash
# Isolated PCS dev environment (avoids global pip dependency conflicts).
# Usage: ./scripts/setup_pcs_dev.sh              # PCS tests only (tests/pcs)
#        ./scripts/setup_pcs_dev.sh --include-env  # + PettingZoo for full pytest
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VENV="${VENV:-$ROOT/.venv-pcs}"
PCS_CORE="${PCS_CORE_PATH:-$(cd "$ROOT/../pcs-core/python" 2>/dev/null && pwd || true)}"
INCLUDE_ENV=0
if [[ "${1:-}" == "--include-env" ]]; then
  INCLUDE_ENV=1
fi

if [[ -z "$PCS_CORE" || ! -d "$PCS_CORE" ]]; then
  echo "pcs-core not found. Set PCS_CORE_PATH to pcs-core/python" >&2
  exit 1
fi

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -U pip wheel
pip install -e "$PCS_CORE"
if [[ "$INCLUDE_ENV" -eq 1 ]]; then
  pip install -e ".[dev,env,pcs]"
else
  pip install -e ".[dev,pcs]"
fi
pip install "referencing>=0.35.0,<0.37.0"
echo ""
echo "PCS dev environment ready. Activate with: source $VENV/bin/activate"
echo "Then run:  pytest tests/pcs -q"
echo "           bash examples/pcs_qc_release/scripts/run_pcs_ci_local.sh"
echo "           labtrust run-demo qc-release"
if [[ "$INCLUDE_ENV" -eq 1 ]]; then
  echo "Full suite: pytest -q"
else
  echo "Full suite needs env: ./scripts/setup_pcs_dev.sh --include-env"
fi
