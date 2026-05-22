#!/usr/bin/env bash
# Full PCS CI parity locally (matches .github/workflows/pcs.yml).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PCS_DETERMINISTIC=1

PYTHON="${PYTHON:-python}"
if [ -x "$ROOT/.venv-pcs/bin/python" ]; then
  PYTHON="$ROOT/.venv-pcs/bin/python"
fi

PCS_CORE="${PCS_CORE_PATH:-$ROOT/../pcs-core}"
if [ -d "$PCS_CORE/schemas" ]; then
  "$PYTHON" scripts/apply_pcs_core_labtrust_schema_profiles.py --pcs-core "$PCS_CORE"
fi

PCS_BENCH="${PCS_BENCH_PATH:-$ROOT/../pcs-bench}"

"$PYTHON" -m pytest tests/pcs -q
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_workflow_profile.py
if [ -d "$PCS_CORE/python" ]; then
  "$PYTHON" -m pcs_core.hash_vectors --verify
fi
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_release_fixtures.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_regeneration_report.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_failure_manifests.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_formalization.py

labtrust generate-benchmark-cases \
  --workflow hospital_lab.qc_release \
  --out /tmp/labtrust-bench \
  --release-dir examples/pcs_qc_release/release \
  --seed 42
labtrust verify-benchmark-cases --benchmark-dir /tmp/labtrust-bench

if [ -d "$PCS_CORE" ]; then
  labtrust generate-benchmark-cases \
    --workflow hospital_lab.qc_release \
    --out /tmp/labtrust-bench-layout \
    --release-dir examples/pcs_qc_release/release \
    --pcs-bench-layout \
    --seed 42 \
    --validate-pcs-core-output "$PCS_CORE"
  labtrust verify-benchmark-cases \
    --benchmark-dir /tmp/labtrust-bench-layout \
    --validate-pcs-core-output "$PCS_CORE"
fi

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

if command -v pcs >/dev/null 2>&1; then
  pcs benchmark validate || true
elif [ -d "$PCS_CORE/python" ]; then
  "$PYTHON" -m pcs_core.cli benchmark validate || true
fi

"$PYTHON" examples/pcs_qc_release/scripts/ci_benchmark_reproducibility.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_benchmark_ingest_golden.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_pcs_bench_ingest_fixture.py
"$PYTHON" scripts/generate_pcs_bench_ingest_fixture.py
"$PYTHON" examples/pcs_qc_release/scripts/ci_validate_pcs_producer_contract.py

if [ -d "$PCS_CORE" ] && command -v labtrust >/dev/null 2>&1; then
  labtrust validate-pcs-producer \
    --dir tests/fixtures/pcs_bench_reproducibility \
    --pcs-core "$PCS_CORE"
fi
if command -v pcs-bench >/dev/null 2>&1 && [ -d "$PCS_CORE" ]; then
  pcs-bench validate-ingest \
    --input tests/fixtures/pcs_bench_reproducibility/pcs_bench_ingest.v0.json \
    --pcs-core "$PCS_CORE"
fi

"$PYTHON" examples/pcs_qc_release/scripts/generate_benchmark_packet.py

if [ -d "$PCS_CORE/examples/labtrust-release" ]; then
  labtrust verify-release-protocol \
    --release-dir examples/pcs_qc_release/release \
    --pcs-core "$PCS_CORE/examples/labtrust-release"
fi

labtrust check-status-policy \
  --release-dir examples/pcs_qc_release/release \
  --json

labtrust generate-failure-gallery \
  --workflow hospital_lab.qc_release \
  --out examples/pcs_qc_release/failures \
  --release-dir examples/pcs_qc_release/release
"$PYTHON" examples/pcs_qc_release/scripts/validate_failure_gallery.py

if command -v pcs >/dev/null 2>&1; then
  pcs registry check-artifact examples/pcs_qc_release/release/handoff_to_certifyedge.json
  pcs registry check-artifact examples/pcs_qc_release/release/handoff_to_pf.json
  pcs validate examples/pcs_qc_release/release/labtrust_release_fragment.json
  pcs registry check-artifact examples/pcs_qc_release/release/labtrust_release_fragment.json
fi

if [ -d "$PCS_CORE/examples/labtrust-release" ]; then
  "$PYTHON" -m labtrust_gym.pcs.sync_pcs_core_rc \
    --verify-only \
    --pcs-core "$PCS_CORE/examples/labtrust-release"
fi

bash examples/pcs_qc_release/scripts/labtrust_only_smoke.sh

export PCS_DETERMINISTIC=1
labtrust run-demo qc-release-invalid-missing-qc --deterministic --out /tmp/missing-qc
labtrust run-demo qc-release-invalid-unauthorized --deterministic --out /tmp/unauthorized
labtrust export-runtime-receipt --run /tmp/missing-qc --out /tmp/missing_qc_receipt.json
labtrust export-runtime-receipt --run /tmp/unauthorized --out /tmp/unauthorized_receipt.json
"$PYTHON" -c "
import json
from pcs_core.validate import validate_artifact
for p in ('/tmp/missing_qc_receipt.json', '/tmp/unauthorized_receipt.json'):
    r = json.load(open(p))
    assert r['run_outcome'] == 'failed', p
    assert r['status'] == 'RuntimeObserved', p
    validate_artifact(r)
    print('OK', p, r['final_reason_code'])
"

echo "PCS local CI OK"
