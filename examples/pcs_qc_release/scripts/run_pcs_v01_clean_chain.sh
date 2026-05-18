#!/usr/bin/env bash
# PCS v0.1 clean-checkout chain (LabTrust -> CertifyEdge -> PF -> Scientific Memory).
# Run from a fresh LabTrust-Gym clone with sibling repos or set env overrides.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_pcs_chain_env.sh
source "$SCRIPT_DIR/_pcs_chain_env.sh"

LABTRUST_ONLY=0
SKIP_SCIENTIFIC_MEMORY=0
for arg in "$@"; do
  case "$arg" in
    --labtrust-only) LABTRUST_ONLY=1 ;;
    --skip-scientific-memory) SKIP_SCIENTIFIC_MEMORY=1 ;;
    -h|--help)
      echo "Usage: $0 [--labtrust-only] [--skip-scientific-memory]"
      echo "Env: CERTIFYEDGE_ROOT, CERTIFYEDGE_BIN, CERTIFYEDGE_SPEC, PF_BIN,"
      echo "     SCIENTIFIC_MEMORY_ROOT, PCS_CHAIN_WORK, CLAIM_ID, PCS_DETERMINISTIC"
      exit 0
      ;;
  esac
done

pcs_chain_init

pcs_require_cmd labtrust
pcs_require_cmd pcs
pcs_require_cmd python

mkdir -p "$WORK" "$RUN_DIR"

pcs_step "LabTrust-Gym: deterministic demos"
labtrust run-demo qc-release --deterministic --out "$RUN_DIR"
labtrust run-demo qc-release-invalid-missing-qc --deterministic
labtrust run-demo qc-release-invalid-unauthorized --deterministic

pcs_step "LabTrust-Gym: export PCS artifacts"
labtrust export-trace --run "$RUN_DIR" --out "$TRACE_JSON"
labtrust export-runtime-receipt --run "$RUN_DIR" --out "$RUNTIME_RECEIPT_JSON"
labtrust export-pcs --run "$RUN_DIR" --out "$PENDING_JSON"
pcs validate "$PENDING_JSON"

HANDOFF_CE_JSON="${WORK}/labtrust_to_certifyedge_handoff.json"
pcs_step "LabTrust-Gym: HandoffManifest.v0 (runtime_to_certificate) for CertifyEdge"
labtrust emit-handoff-to-certifyedge \
  --trace "$TRACE_JSON" \
  --runtime-receipt "$RUNTIME_RECEIPT_JSON" \
  --out "$HANDOFF_CE_JSON" \
  --release-mode
pcs validate "$HANDOFF_CE_JSON"
cp -f "$HANDOFF_CE_JSON" "${WORK}/handoff_to_certifyedge.json"

if [ "$LABTRUST_ONLY" -eq 1 ]; then
  pcs_step "LabTrust-only chain OK"
  python "$SCRIPT_DIR/verify_pcs_v01_chain.py" --work "$WORK" --stage labtrust
  exit 0
fi

pcs_require_cmd "$CERTIFYEDGE_BIN"
if [ ! -f "$CERTIFYEDGE_SPEC" ]; then
  echo "error: CertifyEdge spec not found: $CERTIFYEDGE_SPEC" >&2
  exit 1
fi

HANDOFF_OUT_JSON="${WORK}/certifyedge_to_labtrust_handoff.json"
pcs_step "CertifyEdge: emit and verify TraceCertificate (HandoffManifest input)"
"$CERTIFYEDGE_BIN" --release-mode emit-pcs-certificate \
  --handoff "$HANDOFF_CE_JSON" \
  --out "$TRACE_CERT_JSON" \
  --handoff-out "$HANDOFF_OUT_JSON"
pcs validate "$TRACE_CERT_JSON"
"$CERTIFYEDGE_BIN" verify-certificate "$TRACE_CERT_JSON" --trace "$TRACE_JSON"

pcs_step "LabTrust-Gym: attach certificate"
labtrust attach-certificate \
  --bundle "$PENDING_JSON" \
  --certificate "$TRACE_CERT_JSON" \
  --out "$CERTIFIED_JSON"
pcs validate "$CERTIFIED_JSON"

pcs_require_cmd "$PF_BIN"

pcs_step "LabTrust: write PF HandoffManifest.v0 (release-run manifests)"
python "$SCRIPT_DIR/finalize_release_run.py" --run-dir "$WORK" --no-promote

pcs_step "Provability Fabric: verify and sign (handoff certified bundle)"
python -c "
from pathlib import Path
from labtrust_gym.pcs.handoff_manifest import HANDOFF_TO_PF_NAME
from labtrust_gym.pcs.release_run import validate_handoff_directory
work = Path('$WORK')
validate_handoff_directory(work)
handoff = __import__('json').loads((work / HANDOFF_TO_PF_NAME).read_text())
cert_name = 'science_claim_bundle.certified.json'
cert = work / cert_name
if not cert.is_file():
    raise SystemExit(f'missing PF input bundle: {cert}')
print('OK PF input', cert.name, 'certificate_id', handoff['invariants']['certificate_id'])
"

"$PF_BIN" verify science-claim "$CERTIFIED_JSON" --out "$VERIFICATION_JSON"
pcs validate "$VERIFICATION_JSON"
"$PF_BIN" sign science-claim "$CERTIFIED_JSON" --out "$SIGNED_JSON"
pcs validate "$SIGNED_JSON"
"$PF_BIN" inspect science-claim "$SIGNED_JSON"

if [ "$SKIP_SCIENTIFIC_MEMORY" -eq 1 ]; then
  pcs_step "Skipping Scientific Memory (--skip-scientific-memory)"
else
  pcs_require_cmd just
  if [ ! -f "$SCIENTIFIC_MEMORY_ROOT/justfile" ]; then
    echo "error: scientific-memory justfile not found: $SCIENTIFIC_MEMORY_ROOT/justfile" >&2
    exit 1
  fi
  pcs_step "Scientific Memory: import and render"
  (
    cd "$SCIENTIFIC_MEMORY_ROOT"
    just pcs-import-bundle "$SIGNED_JSON"
    just pcs-render-claim "$CLAIM_ID"
  )
fi

pcs_step "Validate chain artifacts"
python "$SCRIPT_DIR/verify_pcs_v01_chain.py" --work "$WORK" --stage full

# Optional: atomically promote release-run -> release/ (+ handoff/)
if [ "${PCS_COPY_TO_RELEASE:-0}" = "1" ]; then
  RELEASE="$PCS_CHAIN_ROOT/examples/pcs_qc_release/release"
  export PCS_MANIFEST_GENERATOR="run_pcs_v01_clean_chain.sh"
  export CERTIFYEDGE_ROOT
  export CERTIFYEDGE_BIN
  export CERTIFYEDGE_SPEC
  python "$SCRIPT_DIR/finalize_release_run.py" --run-dir "$WORK" --release-dir "$RELEASE"
  python "$SCRIPT_DIR/ci_validate_release_fixtures.py"
  echo "promoted release-run to $RELEASE (handoff/ + downstream artifacts)"
fi

echo ""
echo "PCS v0.1 clean-checkout chain OK (workdir=$WORK)"
