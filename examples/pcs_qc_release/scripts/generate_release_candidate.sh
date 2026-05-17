#!/usr/bin/env bash
# Build examples/pcs_qc_release/release/ via atomic release-run staging + handoff promotion.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PCS_DETERMINISTIC=1
export PCS_RELEASE_FIXTURE=1

RELEASE="${PCS_RELEASE_DIR:-$ROOT/examples/pcs_qc_release/release}"
RELEASE_RUN="${PCS_RELEASE_RUN_DIR:-$ROOT/examples/pcs_qc_release/release-run}"
RUN_DIR="${PCS_RUN_DIR:-$ROOT/runs/qc-release}"

CERTIFYEDGE_ROOT="${CERTIFYEDGE_ROOT:-$ROOT/../CertifyEdge}"
CERTIFYEDGE_BIN="${CERTIFYEDGE_BIN:-certifyedge}"
CERTIFYEDGE_SPEC="${CERTIFYEDGE_SPEC:-$CERTIFYEDGE_ROOT/templates/hospital_lab/qc_release.stl}"
PCS_CORE_ROOT="${PCS_CORE_PATH:-$ROOT/../pcs-core}"
if [ "$(basename "$PCS_CORE_ROOT")" = "python" ]; then
  PCS_CORE_GIT_ROOT="$(cd "$(dirname "$PCS_CORE_ROOT")" && pwd)"
else
  PCS_CORE_GIT_ROOT="$(cd "$PCS_CORE_ROOT" && pwd)"
fi

CERTIFYEDGE_COMMIT="$(git -C "$CERTIFYEDGE_ROOT" rev-parse HEAD)"
export CERTIFYEDGE_SOURCE_COMMIT="$CERTIFYEDGE_COMMIT"

if ! command -v labtrust >/dev/null 2>&1; then
  if [ -x "$ROOT/.venv-pcs/bin/labtrust" ]; then
    export PATH="$ROOT/.venv-pcs/bin:$PATH"
  elif [ -x "$ROOT/.venv-pcs/Scripts/labtrust.exe" ]; then
    export PATH="$ROOT/.venv-pcs/Scripts:$PATH"
  fi
fi

if ! command -v "$CERTIFYEDGE_BIN" >/dev/null 2>&1; then
  if [ -x "$CERTIFYEDGE_ROOT/target/debug/certifyedge" ]; then
    CERTIFYEDGE_BIN="$CERTIFYEDGE_ROOT/target/debug/certifyedge"
  elif [ -x "$CERTIFYEDGE_ROOT/target/debug/certifyedge.exe" ]; then
    CERTIFYEDGE_BIN="$CERTIFYEDGE_ROOT/target/debug/certifyedge.exe"
  else
    echo "error: CertifyEdge binary not found: $CERTIFYEDGE_BIN" >&2
    exit 1
  fi
fi
if [ ! -f "$CERTIFYEDGE_SPEC" ]; then
  echo "error: CertifyEdge spec not found: $CERTIFYEDGE_SPEC" >&2
  exit 1
fi

echo "labtrust_gym_commit=$(git -C "$ROOT" rev-parse HEAD)"
echo "certifyedge_commit=$CERTIFYEDGE_COMMIT"
echo "pcs_core_commit=$(git -C "$PCS_CORE_GIT_ROOT" rev-parse HEAD)"

rm -rf "$RELEASE_RUN"
mkdir -p "$RELEASE_RUN"

labtrust run-demo qc-release --deterministic --out "$RUN_DIR"
labtrust export-trace --run "$RUN_DIR" --out "$RELEASE_RUN/trace.json"
labtrust export-runtime-receipt --run "$RUN_DIR" --out "$RELEASE_RUN/runtime_receipt.json"
labtrust export-pcs --run "$RUN_DIR" --out "$RELEASE_RUN/science_claim_bundle.pending.json"

CERTIFYEDGE_SOURCE_COMMIT="$CERTIFYEDGE_COMMIT" \
  "$CERTIFYEDGE_BIN" --release-mode emit-pcs-certificate \
  --spec "$CERTIFYEDGE_SPEC" \
  --trace "$RELEASE_RUN/trace.json" \
  --out "$RELEASE_RUN/trace_certificate.json"
pcs validate "$RELEASE_RUN/trace_certificate.json"
"$CERTIFYEDGE_BIN" verify-certificate "$RELEASE_RUN/trace_certificate.json" --trace "$RELEASE_RUN/trace.json"

labtrust attach-certificate \
  --bundle "$RELEASE_RUN/science_claim_bundle.pending.json" \
  --certificate "$RELEASE_RUN/trace_certificate.json" \
  --out "$RELEASE_RUN/science_claim_bundle.certified.json"

pcs validate "$RELEASE_RUN/science_claim_bundle.certified.json"
python "$ROOT/examples/pcs_qc_release/scripts/verify_pcs_v01_chain.py" --work "$RELEASE_RUN" --stage certified

export PCS_MANIFEST_GENERATOR="generate_release_candidate.sh"
export CERTIFYEDGE_ROOT="$CERTIFYEDGE_ROOT"
export CERTIFYEDGE_BIN="$CERTIFYEDGE_BIN"
export CERTIFYEDGE_SPEC="$CERTIFYEDGE_SPEC"
python "$ROOT/examples/pcs_qc_release/scripts/finalize_release_run.py" \
  --run-dir "$RELEASE_RUN" \
  --release-dir "$RELEASE"

python "$ROOT/examples/pcs_qc_release/scripts/ci_validate_release_fixtures.py"
echo "Release candidate promoted from release-run to $RELEASE (handoff/ + flat artifacts)"
