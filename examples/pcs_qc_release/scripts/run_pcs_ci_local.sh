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
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_workflow_profile.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_release_fixtures.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_regeneration_report.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_failure_manifests.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_formalization.py
labtrust generate-benchmark-cases \
  --workflow hospital_lab.qc_release \
  --out examples/pcs_qc_release/benchmark \
  --release-dir examples/pcs_qc_release/release \
  --seed 42
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_benchmark_cases.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_benchmark_pcs_core.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_benchmark_pcs_bench_layout.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_benchmark_registry_expected.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_pcs_core_labtrust_suite.py
"$PYTHON" examples/pcs_qc_release/scripts/generate_benchmark_packet.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_benchmark_reproducibility.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_benchmark_ingest_golden.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_pcs_bench_ingest_fixture.py
"$PYTHON" -m labtrust_gym.cli.main check-status-policy \
  --release-dir examples/pcs_qc_release/release
labtrust generate-failure-gallery \
  --workflow hospital_lab.qc_release \
  --out examples/pcs_qc_release/failures \
  --release-dir examples/pcs_qc_release/release
"$PYTHON" examples/pcs_qc_release/scripts/validate_failure_gallery.py
PCS_CANON="${PCS_CORE_PATH:-$ROOT/../pcs-core}/examples/labtrust-release"
if [ -f "$PCS_CANON/trace.json" ]; then
  "$PYTHON" -m labtrust_gym.cli.main verify-release-protocol \
    --release-dir examples/pcs_qc_release/release \
    --pcs-core "$PCS_CANON"
fi
echo "PCS local CI OK"
