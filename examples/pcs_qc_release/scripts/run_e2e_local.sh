#!/usr/bin/env bash
# Deprecated alias: use run_pcs_v01_clean_chain.sh --labtrust-only
set -euo pipefail
exec "$(dirname "$0")/run_pcs_v01_clean_chain.sh" --labtrust-only "$@"
