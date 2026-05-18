#!/usr/bin/env bash
# Regenerate the full LabTrust PCS Phase 2 protocol package (not mirror-only sync).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

export PCS_DETERMINISTIC=1
export PCS_RELEASE_FIXTURE=1

RELEASE="${PCS_RELEASE_DIR:-$ROOT/examples/pcs_qc_release/release}"
PCS_CORE="${PCS_CORE_PATH:-$ROOT/../pcs-core}"
if [ "$(basename "$PCS_CORE")" = "python" ]; then
  PCS_CORE="$(cd "$(dirname "$PCS_CORE")" && pwd)"
else
  PCS_CORE="$(cd "$PCS_CORE" && pwd)"
fi
CERTIFYEDGE_BIN="${CERTIFYEDGE_BIN:-certifyedge}"

if ! command -v labtrust >/dev/null 2>&1; then
  export PATH="$ROOT/.venv-pcs/bin:$ROOT/.venv-pcs/Scripts:$PATH"
fi

labtrust regenerate-release-protocol \
  --out "$RELEASE" \
  --certifyedge-bin "$CERTIFYEDGE_BIN" \
  --pcs-core "$PCS_CORE"

labtrust verify-release-protocol \
  --release-dir "$RELEASE" \
  --pcs-core "$PCS_CORE/examples/labtrust-release"

echo "OK LabTrust protocol package at $RELEASE"
