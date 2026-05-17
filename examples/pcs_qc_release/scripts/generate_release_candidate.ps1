# Build examples/pcs_qc_release/release/ using real CertifyEdge TraceCertificate output.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"

$Release = if ($env:PCS_RELEASE_DIR) { $env:PCS_RELEASE_DIR } else { Join-Path $Root "examples\pcs_qc_release\release" }
$RunDir = if ($env:PCS_RUN_DIR) { $env:PCS_RUN_DIR } else { Join-Path $Root "runs\qc-release" }
$Work = if ($env:PCS_RELEASE_WORK) { $env:PCS_RELEASE_WORK } else { Join-Path $Root "tmp_pcs_release_candidate" }

$CertifyEdgeRoot = if ($env:CERTIFYEDGE_ROOT) { $env:CERTIFYEDGE_ROOT } else { Join-Path (Split-Path -Parent $Root) "CertifyEdge" }
$CertifyEdgeBin = if ($env:CERTIFYEDGE_BIN) { $env:CERTIFYEDGE_BIN } else { "certifyedge" }
$CertifyEdgeSpec = if ($env:CERTIFYEDGE_SPEC) {
    $env:CERTIFYEDGE_SPEC
} else {
    Join-Path $CertifyEdgeRoot "templates\hospital_lab\qc_release.stl"
}

$Labtrust = Get-PcsTool "labtrust"
$Python = Get-PcsTool "python"

$CeCmd = Get-Command $CertifyEdgeBin -ErrorAction SilentlyContinue
if (-not $CeCmd) {
    $candidate = Join-Path $CertifyEdgeRoot "Scripts\$CertifyEdgeBin.exe"
    if (Test-Path $candidate) { $CertifyEdgeBin = $candidate } else { throw "CertifyEdge not found: $CertifyEdgeBin" }
}
if (-not (Test-Path $CertifyEdgeSpec)) {
    throw "CertifyEdge spec not found: $CertifyEdgeSpec (set CERTIFYEDGE_SPEC or CERTIFYEDGE_ROOT)"
}

if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
New-Item -ItemType Directory -Force -Path $Work, $Release | Out-Null

& $Labtrust run-demo qc-release --deterministic --out $RunDir
& $Labtrust export-trace --run $RunDir --out (Join-Path $Work "trace.json")
& $Labtrust export-runtime-receipt --run $RunDir --out (Join-Path $Work "runtime_receipt.json")
& $Labtrust export-pcs --run $RunDir --out (Join-Path $Work "science_claim_bundle.pending.json")

& $CertifyEdgeBin emit-pcs-certificate `
    --spec $CertifyEdgeSpec `
    --trace (Join-Path $Work "trace.json") `
    --out (Join-Path $Work "trace_certificate.json")
& $Pcs validate (Join-Path $Work "trace_certificate.json")
& $CertifyEdgeBin verify-certificate (Join-Path $Work "trace_certificate.json") --trace (Join-Path $Work "trace.json")

& $Labtrust attach-certificate `
    --bundle (Join-Path $Work "science_claim_bundle.pending.json") `
    --certificate (Join-Path $Work "trace_certificate.json") `
    --out (Join-Path $Work "science_claim_bundle.certified.json")

@(
    "trace.json",
    "runtime_receipt.json",
    "trace_certificate.json",
    "science_claim_bundle.pending.json",
    "science_claim_bundle.certified.json"
) | ForEach-Object {
    Copy-Item (Join-Path $Work $_) (Join-Path $Release $_) -Force
}

$env:PCS_RELEASE_DIR = $Release
& $Python -c @"
import json, os
from datetime import datetime, timezone
from pathlib import Path
release = Path(os.environ['PCS_RELEASE_DIR'])
cert = json.loads((release / 'trace_certificate.json').read_text(encoding='utf-8'))
manifest = {
    'schema_version': 'v0',
    'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'generator': 'generate_release_candidate.ps1',
    'mock_certificate': False,
    'certifyedge_bin': os.environ.get('CERTIFYEDGE_BIN', 'certifyedge'),
    'certifyedge_spec': os.environ.get('CERTIFYEDGE_SPEC', ''),
    'certificate_id': cert.get('certificate_id'),
    'certificate_source_repo': cert.get('source_repo'),
}
(release / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
"@

& $Pcs validate (Join-Path $Work "science_claim_bundle.certified.json")
& $Python (Join-Path $PSScriptRoot "verify_pcs_v01_chain.py") --work $Work --stage certified
& $Python -c "from pathlib import Path; from labtrust_gym.pcs.release_fixtures import validate_release_fixtures; print('validated', validate_release_fixtures(Path(r'$Release')))"

Write-Host "Release candidate fixtures written to $Release"
