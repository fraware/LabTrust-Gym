# Build examples/pcs_qc_release/release/ via atomic release-run staging + handoff promotion.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = "1"
$env:PCS_RELEASE_FIXTURE = "1"

$Release = if ($env:PCS_RELEASE_DIR) { $env:PCS_RELEASE_DIR } else { Join-Path $Root "examples\pcs_qc_release\release" }
$ReleaseRun = if ($env:PCS_RELEASE_RUN_DIR) { $env:PCS_RELEASE_RUN_DIR } else { Join-Path $Root "examples\pcs_qc_release\release-run" }
$RunDir = if ($env:PCS_RUN_DIR) { $env:PCS_RUN_DIR } else { Join-Path $Root "runs\qc-release" }

$CertifyEdgeRoot = if ($env:CERTIFYEDGE_ROOT) { $env:CERTIFYEDGE_ROOT } else { Join-Path (Split-Path -Parent $Root) "CertifyEdge" }
$CertifyEdgeBin = if ($env:CERTIFYEDGE_BIN) { $env:CERTIFYEDGE_BIN } else { "certifyedge" }
$CertifyEdgeSpec = if ($env:CERTIFYEDGE_SPEC) { $env:CERTIFYEDGE_SPEC } else { Join-Path $CertifyEdgeRoot "templates\hospital_lab\qc_release.stl" }
if (-not [System.IO.Path]::IsPathRooted($CertifyEdgeSpec)) {
    $CertifyEdgeSpec = Join-Path $CertifyEdgeRoot ($CertifyEdgeSpec -replace '^CertifyEdge[\\/]', '')
}

$Labtrust = Get-PcsTool "labtrust"
$Python = Get-PcsTool "python"
$Parent = Split-Path -Parent $Root

$PcsExe = Join-Path $Root ".venv-pcs\Scripts\pcs.exe"
$script:PcsInvokePrefix = $null
if (-not (Test-Path $PcsExe)) {
    $PcsCmd = Get-Command pcs -ErrorAction SilentlyContinue
    if ($PcsCmd) { $PcsExe = $PcsCmd.Source } else {
        $PcsExe = $Python
        $script:PcsInvokePrefix = @("-m", "pcs_core.cli")
    }
}
function Invoke-PcsValidate {
    param([string]$ArtifactPath)
    if ($script:PcsInvokePrefix) { & $PcsExe @script:PcsInvokePrefix validate $ArtifactPath }
    else { & $PcsExe validate $ArtifactPath }
    if ($LASTEXITCODE -ne 0) { throw "pcs validate failed: $ArtifactPath" }
}

$CeCmd = Get-Command $CertifyEdgeBin -ErrorAction SilentlyContinue
if (-not $CeCmd) {
    $candidate = Join-Path $CertifyEdgeRoot "target\debug\certifyedge.exe"
    if (Test-Path $candidate) { $CertifyEdgeBin = $candidate } else { throw "CertifyEdge not found: $CertifyEdgeBin" }
}
if (-not (Test-Path $CertifyEdgeSpec)) { throw "CertifyEdge spec not found: $CertifyEdgeSpec" }

$PcsCoreRoot = if ($env:PCS_CORE_PATH) { $env:PCS_CORE_PATH } else { Join-Path $Parent "pcs-core" }
$PcsCoreGitRoot = if ((Split-Path -Leaf $PcsCoreRoot) -eq "python") { Split-Path -Parent $PcsCoreRoot } else { $PcsCoreRoot }
$CertifyEdgeCommit = (git -C $CertifyEdgeRoot rev-parse HEAD).Trim()
$env:CERTIFYEDGE_SOURCE_COMMIT = $CertifyEdgeCommit
Write-Host "labtrust_gym_commit=$((git -C $Root rev-parse HEAD).Trim())"
Write-Host "certifyedge_commit=$CertifyEdgeCommit"
Write-Host "pcs_core_commit=$((git -C $PcsCoreGitRoot rev-parse HEAD).Trim())"

if (Test-Path $ReleaseRun) { Remove-Item -Recurse -Force $ReleaseRun }
New-Item -ItemType Directory -Force -Path $ReleaseRun | Out-Null

& $Labtrust run-demo qc-release --deterministic --out $RunDir
& $Labtrust export-trace --run $RunDir --out (Join-Path $ReleaseRun "trace.json")
& $Labtrust export-runtime-receipt --run $RunDir --out (Join-Path $ReleaseRun "runtime_receipt.json")
& $Labtrust export-pcs --run $RunDir --out (Join-Path $ReleaseRun "science_claim_bundle.pending.json")

$env:CERTIFYEDGE_SOURCE_COMMIT = $CertifyEdgeCommit
& $CertifyEdgeBin --release-mode emit-pcs-certificate `
    --spec $CertifyEdgeSpec `
    --trace (Join-Path $ReleaseRun "trace.json") `
    --out (Join-Path $ReleaseRun "trace_certificate.json")
Invoke-PcsValidate (Join-Path $ReleaseRun "trace_certificate.json")
& $CertifyEdgeBin verify-certificate (Join-Path $ReleaseRun "trace_certificate.json") --trace (Join-Path $ReleaseRun "trace.json")

& $Labtrust attach-certificate `
    --bundle (Join-Path $ReleaseRun "science_claim_bundle.pending.json") `
    --certificate (Join-Path $ReleaseRun "trace_certificate.json") `
    --out (Join-Path $ReleaseRun "science_claim_bundle.certified.json")

Invoke-PcsValidate (Join-Path $ReleaseRun "science_claim_bundle.certified.json")
& $Python (Join-Path $PSScriptRoot "verify_pcs_v01_chain.py") --work $ReleaseRun --stage certified

$env:PCS_MANIFEST_GENERATOR = "generate_release_candidate.ps1"
$env:CERTIFYEDGE_ROOT = $CertifyEdgeRoot
$env:CERTIFYEDGE_BIN = $CertifyEdgeBin
$env:CERTIFYEDGE_SPEC = $CertifyEdgeSpec
& $Python (Join-Path $PSScriptRoot "finalize_release_run.py") --run-dir $ReleaseRun --release-dir $Release
& $Python (Join-Path $PSScriptRoot "ci_validate_release_fixtures.py")

Write-Host "Release candidate promoted from release-run to $Release"
