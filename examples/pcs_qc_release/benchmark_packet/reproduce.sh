#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
python examples/pcs_qc_release/scripts/generate_benchmark_packet.py
echo "benchmark packet reproduce OK"
