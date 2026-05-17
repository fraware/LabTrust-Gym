#!/usr/bin/env bash
# Build examples/pcs_qc_release/release/ using real CertifyEdge TraceCertificate output.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PCS_DETERMINISTIC=1

RELEASE="${PCS_RELEASE_DIR:-$ROOT/examples/pcs_qc_release/release}"
RUN_DIR="${PCS_RUN_DIR:-$ROOT/runs/qc-release}"
WORK="${PCS_RELEASE_WORK:-$ROOT/tmp_pcs_release_candidate}"

CERTIFYEDGE_ROOT="${CERTIFYEDGE_ROOT:-$ROOT/../CertifyEdge}"
CERTIFYEDGE_BIN="${CERTIFYEDGE_BIN:-certifyedge}"
CERTIFYEDGE_SPEC="${CERTIFYEDGE_SPEC:-$CERTIFYEDGE_ROOT/templates/hospital_lab/qc_release.stl}"

if ! command -v labtrust >/dev/null 2>&1; then
  if [ -x "$ROOT/.venv-pcs/bin/labtrust" ]; then
    export PATH="$ROOT/.venv-pcs/bin:$PATH"
  elif [ -x "$ROOT/.venv-pcs/Scripts/labtrust.exe" ]; then
    export PATH="$ROOT/.venv-pcs/Scripts:$PATH"
  fi
fi

if ! command -v "$CERTIFYEDGE_BIN" >/dev/null 2>&1; then
  echo "error: CertifyEdge binary not found: $CERTIFYEDGE_BIN" >&2
  echo "Set CERTIFYEDGE_BIN or install CertifyEdge; see release/README.md" >&2
  exit 1
fi
if [ ! -f "$CERTIFYEDGE_SPEC" ]; then
  echo "error: CertifyEdge spec not found: $CERTIFYEDGE_SPEC" >&2
  echo "Set CERTIFYEDGE_SPEC or CERTIFYEDGE_ROOT (default: $CERTIFYEDGE_ROOT)" >&2
  exit 1
fi

rm -rf "$WORK"
mkdir -p "$WORK" "$RELEASE"

labtrust run-demo qc-release --deterministic --out "$RUN_DIR"
labtrust export-trace --run "$RUN_DIR" --out "$WORK/trace.json"
labtrust export-runtime-receipt --run "$RUN_DIR" --out "$WORK/runtime_receipt.json"
labtrust export-pcs --run "$RUN_DIR" --out "$WORK/science_claim_bundle.pending.json"

"$CERTIFYEDGE_BIN" emit-pcs-certificate \
  --spec "$CERTIFYEDGE_SPEC" \
  --trace "$WORK/trace.json" \
  --out "$WORK/trace_certificate.json"
pcs validate "$WORK/trace_certificate.json"
"$CERTIFYEDGE_BIN" verify-certificate "$WORK/trace_certificate.json" --trace "$WORK/trace.json"

labtrust attach-certificate \
  --bundle "$WORK/science_claim_bundle.pending.json" \
  --certificate "$WORK/trace_certificate.json" \
  --out "$WORK/science_claim_bundle.certified.json"

for f in trace.json runtime_receipt.json trace_certificate.json \
  science_claim_bundle.pending.json science_claim_bundle.certified.json; do
  cp "$WORK/$f" "$RELEASE/$f"
done

export PCS_RELEASE_DIR="$RELEASE"
export PCS_MANIFEST_GENERATOR="generate_release_candidate.sh"
export CERTIFYEDGE_ROOT="$CERTIFYEDGE_ROOT"
python -c "
from pathlib import Path
from labtrust_gym.pcs.release_fixtures import write_trace_hash_alignment
write_trace_hash_alignment(Path('$RELEASE'))
print('OK trace_hash_alignment.json')
"
python "$ROOT/examples/pcs_qc_release/scripts/write_release_manifest.py"

pcs validate "$WORK/science_claim_bundle.certified.json"
python "$ROOT/examples/pcs_qc_release/scripts/verify_pcs_v01_chain.py" --work "$WORK" --stage certified
python "$ROOT/examples/pcs_qc_release/scripts/ci_validate_release_fixtures.py"

echo "Release candidate fixtures written to $RELEASE"
