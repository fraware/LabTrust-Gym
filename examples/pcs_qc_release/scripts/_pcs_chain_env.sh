# shellcheck shell=bash
# Shared paths for PCS v0.1 clean-checkout chain (source from other scripts).

_pcs_chain_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd
}

pcs_chain_init() {
  PCS_CHAIN_ROOT="${PCS_CHAIN_ROOT:-$(_pcs_chain_root)}"
  cd "$PCS_CHAIN_ROOT"

  export PCS_DETERMINISTIC="${PCS_DETERMINISTIC:-1}"
  export RUN_DIR="${RUN_DIR:-runs/qc-release}"
  export RELEASE_RUN_DIR="${PCS_RELEASE_RUN_DIR:-$PCS_CHAIN_ROOT/examples/pcs_qc_release/release-run}"
  export WORK="${PCS_CHAIN_WORK:-$RELEASE_RUN_DIR}"

  export TRACE_JSON="${WORK}/trace.json"
  export HANDOFF_CE_JSON="${WORK}/labtrust_to_certifyedge_handoff.json"
  export RUNTIME_RECEIPT_JSON="${WORK}/runtime_receipt.json"
  export PENDING_JSON="${WORK}/science_claim_bundle.pending.json"
  export TRACE_CERT_JSON="${WORK}/trace_certificate.json"
  export CERTIFIED_JSON="${WORK}/science_claim_bundle.certified.json"
  export VERIFICATION_JSON="${WORK}/verification_result.json"
  export SIGNED_JSON="${WORK}/signed_science_claim_bundle.json"

  PARENT="$(dirname "$PCS_CHAIN_ROOT")"
  export CERTIFYEDGE_ROOT="${CERTIFYEDGE_ROOT:-$PARENT/CertifyEdge}"
  export CERTIFYEDGE_BIN="${CERTIFYEDGE_BIN:-certifyedge}"
  export CERTIFYEDGE_SPEC="${CERTIFYEDGE_SPEC:-$CERTIFYEDGE_ROOT/templates/hospital_lab/qc_release.stl}"
  export PROVABILITY_FABRIC_ROOT="${PROVABILITY_FABRIC_ROOT:-$PARENT/provability-fabric}"
  export PF_BIN="${PF_BIN:-pf}"

  if [ "$CERTIFYEDGE_BIN" = "certifyedge" ]; then
    for candidate in \
      "$CERTIFYEDGE_ROOT/target/debug/certifyedge" \
      "$CERTIFYEDGE_ROOT/target/release/certifyedge" \
      "$CERTIFYEDGE_ROOT/target/debug/certifyedge.exe" \
      "$CERTIFYEDGE_ROOT/target/release/certifyedge.exe"; do
      if [ -x "$candidate" ]; then
        export CERTIFYEDGE_BIN="$candidate"
        break
      fi
    done
  fi

  if [ "$PF_BIN" = "pf" ]; then
    for candidate in \
      "$PROVABILITY_FABRIC_ROOT/core/cli/pf/pf" \
      "$PROVABILITY_FABRIC_ROOT/core/cli/pf/pf.exe"; do
      if [ -x "$candidate" ]; then
        export PF_BIN="$candidate"
        break
      fi
    done
  fi
  export SCIENTIFIC_MEMORY_ROOT="${SCIENTIFIC_MEMORY_ROOT:-$PARENT/scientific-memory}"
  export CLAIM_ID="${CLAIM_ID:-claim-pcs-qc-release-v0.1}"

  if [ -x "$PCS_CHAIN_ROOT/.venv-pcs/bin/labtrust" ]; then
    export PATH="$PCS_CHAIN_ROOT/.venv-pcs/bin:$PATH"
  elif [ -x "$PCS_CHAIN_ROOT/.venv-pcs/Scripts" ]; then
    export PATH="$PCS_CHAIN_ROOT/.venv-pcs/Scripts:$PATH"
  fi
}

pcs_require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "error: required command not found: $name" >&2
    return 1
  fi
}

pcs_step() {
  echo ""
  echo "==> $*"
}
