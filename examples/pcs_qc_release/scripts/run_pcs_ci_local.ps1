# Full PCS CI parity locally (matches .github/workflows/pcs.yml).
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"

$Python = Get-PcsTool "python"
$Labtrust = Get-PcsTool "labtrust"
$PcsCore = if ($env:PCS_CORE_PATH) { $env:PCS_CORE_PATH } else { Join-Path (Split-Path $Root -Parent) "pcs-core" }
$TmpBench = Join-Path $env:TEMP "labtrust-bench"
$TmpBenchLayout = Join-Path $env:TEMP "labtrust-bench-layout"

function Invoke-PcsStep {
    param([scriptblock]$Block)
    & $Block
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (Test-Path (Join-Path $PcsCore "schemas")) {
    Invoke-PcsStep { & $Python scripts/apply_pcs_core_labtrust_schema_profiles.py --pcs-core $PcsCore }
}

Invoke-PcsStep { & $Python -m pytest tests/pcs -q }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_workflow_profile.py }

if (Test-Path (Join-Path $PcsCore "python")) {
    Invoke-PcsStep { & $Python -m pcs_core.hash_vectors --verify }
}

Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_release_fixtures.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_regeneration_report.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_failure_manifests.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_formalization.py }

Invoke-PcsStep {
    & $Labtrust generate-benchmark-cases `
        --workflow hospital_lab.qc_release `
        --out $TmpBench `
        --release-dir examples/pcs_qc_release/release `
        --seed 42
    & $Labtrust verify-benchmark-cases --benchmark-dir $TmpBench
}

if (Test-Path $PcsCore) {
    Invoke-PcsStep {
        & $Labtrust generate-benchmark-cases `
            --workflow hospital_lab.qc_release `
            --out $TmpBenchLayout `
            --release-dir examples/pcs_qc_release/release `
            --pcs-bench-layout `
            --seed 42 `
            --validate-pcs-core-output $PcsCore
        & $Labtrust verify-benchmark-cases `
            --benchmark-dir $TmpBenchLayout `
            --validate-pcs-core-output $PcsCore
    }
}

Invoke-PcsStep {
    & $Labtrust generate-benchmark-cases `
        --workflow hospital_lab.qc_release `
        --out examples/pcs_qc_release/benchmark `
        --release-dir examples/pcs_qc_release/release `
        --seed 42
}
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_cases.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_pcs_core.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_pcs_bench_layout.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_registry_expected.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_pcs_core_labtrust_suite.py }

Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_benchmark_reproducibility.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_benchmark_ingest_golden.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_pcs_bench_ingest_fixture.py }
Invoke-PcsStep { & $Python scripts/generate_pcs_bench_ingest_fixture.py }
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/ci_validate_pcs_producer_contract.py }

if (Test-Path $PcsCore) {
    Invoke-PcsStep {
        & $Labtrust validate-pcs-producer `
            --dir tests/fixtures/pcs_bench_reproducibility `
            --pcs-core $PcsCore
    }
}
$PcsBench = Get-Command pcs-bench -ErrorAction SilentlyContinue
if ($PcsBench -and (Test-Path $PcsCore)) {
    Invoke-PcsStep {
        pcs-bench validate-ingest `
            --input tests/fixtures/pcs_bench_reproducibility/pcs_bench_ingest.v0.json `
            --pcs-core $PcsCore
    }
}

Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/generate_benchmark_packet.py }

$Canon = Join-Path $PcsCore "examples\labtrust-release"
if (Test-Path (Join-Path $Canon "trace.json")) {
    Invoke-PcsStep {
        & $Labtrust verify-release-protocol `
            --release-dir examples/pcs_qc_release/release `
            --pcs-core $Canon
    }
}

Invoke-PcsStep {
    & $Labtrust check-status-policy `
        --release-dir examples/pcs_qc_release/release `
        --json
}

Invoke-PcsStep {
    & $Labtrust generate-failure-gallery `
        --workflow hospital_lab.qc_release `
        --out examples/pcs_qc_release/failures `
        --release-dir examples/pcs_qc_release/release
}
Invoke-PcsStep { & $Python examples/pcs_qc_release/scripts/validate_failure_gallery.py }

$PcsCli = Get-Command pcs -ErrorAction SilentlyContinue
if ($PcsCli) {
    Invoke-PcsStep {
        pcs registry check-artifact examples/pcs_qc_release/release/handoff_to_certifyedge.json
        pcs registry check-artifact examples/pcs_qc_release/release/handoff_to_pf.json
        pcs validate examples/pcs_qc_release/release/labtrust_release_fragment.json
        pcs registry check-artifact examples/pcs_qc_release/release/labtrust_release_fragment.json
    }
}

if (Test-Path (Join-Path $Canon "trace.json")) {
    Invoke-PcsStep {
        & $Python -m labtrust_gym.pcs.sync_pcs_core_rc `
            --verify-only `
            --pcs-core $Canon
    }
}

Invoke-PcsStep { bash examples/pcs_qc_release/scripts/labtrust_only_smoke.sh }

$MissingQc = Join-Path $env:TEMP "missing-qc"
$Unauthorized = Join-Path $env:TEMP "unauthorized"
Invoke-PcsStep {
    & $Labtrust run-demo qc-release-invalid-missing-qc --deterministic --out $MissingQc
    & $Labtrust run-demo qc-release-invalid-unauthorized --deterministic --out $Unauthorized
    & $Labtrust export-runtime-receipt --run $MissingQc --out (Join-Path $env:TEMP "missing_qc_receipt.json")
    & $Labtrust export-runtime-receipt --run $Unauthorized --out (Join-Path $env:TEMP "unauthorized_receipt.json")
    & $Python -c @"
import json
from pcs_core.validate import validate_artifact
for p in (r'$env:TEMP\missing_qc_receipt.json', r'$env:TEMP\unauthorized_receipt.json'):
    r = json.load(open(p))
    assert r['run_outcome'] == 'failed', p
    assert r['status'] == 'RuntimeObserved', p
    validate_artifact(r)
    print('OK', p, r['final_reason_code'])
"@
}

Write-Host "PCS local CI OK"
