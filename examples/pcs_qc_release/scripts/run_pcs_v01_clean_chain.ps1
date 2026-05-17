# PCS v0.1 clean-checkout chain (LabTrust -> CertifyEdge -> PF -> Scientific Memory).
param(
    [switch]$LabtrustOnly,
    [switch]$SkipScientificMemory
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_pcs_common.ps1")

$Root = Get-PcsRepoRoot
Set-Location $Root
$env:PCS_DETERMINISTIC = if ($env:PCS_DETERMINISTIC) { $env:PCS_DETERMINISTIC } else { "1" }

$Work = if ($env:PCS_CHAIN_WORK) { $env:PCS_CHAIN_WORK } else { $Root }
$RunDir = if ($env:RUN_DIR) { $env:RUN_DIR } else { Join-Path $Root "runs\qc-release" }
$Parent = Split-Path -Parent $Root

$TraceJson = Join-Path $Work "trace.json"
$ReceiptJson = Join-Path $Work "runtime_receipt.json"
$PendingJson = Join-Path $Work "science_claim_bundle.pending.json"
$CertJson = Join-Path $Work "trace_certificate.json"
$CertifiedJson = Join-Path $Work "science_claim_bundle.certified.json"
$VerificationJson = Join-Path $Work "verification_result.json"
$SignedJson = Join-Path $Work "signed_science_claim_bundle.json"

$CertifyEdgeRoot = if ($env:CERTIFYEDGE_ROOT) { $env:CERTIFYEDGE_ROOT } else { Join-Path $Parent "CertifyEdge" }
$PfRoot = if ($env:PROVABILITY_FABRIC_ROOT) { $env:PROVABILITY_FABRIC_ROOT } else { Join-Path $Parent "provability-fabric" }
$CertifyEdgeBin = if ($env:CERTIFYEDGE_BIN) { $env:CERTIFYEDGE_BIN } else { "certifyedge" }
$CertifyEdgeBin = Resolve-PcsChainBinary -DefaultName $CertifyEdgeBin -SiblingCandidates @(
    (Join-Path $CertifyEdgeRoot "target\debug\certifyedge.exe"),
    (Join-Path $CertifyEdgeRoot "target\release\certifyedge.exe"),
    (Join-Path $CertifyEdgeRoot "target\debug\certifyedge"),
    (Join-Path $CertifyEdgeRoot "target\release\certifyedge")
)
$CertifyEdgeSpec = if ($env:CERTIFYEDGE_SPEC) {
    $env:CERTIFYEDGE_SPEC
} else {
    Join-Path $CertifyEdgeRoot "templates\hospital_lab\qc_release.stl"
}
$PfBin = if ($env:PF_BIN) { $env:PF_BIN } else { "pf" }
$PfBin = Resolve-PcsChainBinary -DefaultName $PfBin -SiblingCandidates @(
    (Join-Path $PfRoot "core\cli\pf\pf.exe"),
    (Join-Path $PfRoot "core\cli\pf\pf")
)
$SmRoot = if ($env:SCIENTIFIC_MEMORY_ROOT) { $env:SCIENTIFIC_MEMORY_ROOT } else { Join-Path $Parent "scientific-memory" }
$ClaimId = if ($env:CLAIM_ID) { $env:CLAIM_ID } else { "claim-pcs-qc-release-v0.1" }

$Labtrust = Get-PcsTool "labtrust"
$Pcs = Get-PcsTool "pcs"
$Python = Get-PcsTool "python"

function Step([string]$Msg) { Write-Host ""; Write-Host "==> $Msg" }

New-Item -ItemType Directory -Force -Path $Work, $RunDir | Out-Null

Step "LabTrust-Gym: deterministic demos"
& $Labtrust run-demo qc-release --deterministic --out $RunDir
& $Labtrust run-demo qc-release-invalid-missing-qc --deterministic
& $Labtrust run-demo qc-release-invalid-unauthorized --deterministic

Step "LabTrust-Gym: export PCS artifacts"
& $Labtrust export-trace --run $RunDir --out $TraceJson
& $Labtrust export-runtime-receipt --run $RunDir --out $ReceiptJson
& $Labtrust export-pcs --run $RunDir --out $PendingJson
& $Pcs validate $PendingJson

if ($LabtrustOnly) {
    Step "LabTrust-only chain OK"
    & $Python (Join-Path $PSScriptRoot "verify_pcs_v01_chain.py") --work $Work --stage labtrust
    exit 0
}

$CeCmd = Get-Command $CertifyEdgeBin -ErrorAction SilentlyContinue
if (-not $CeCmd) {
    $exe = Join-Path $CertifyEdgeRoot "Scripts\$CertifyEdgeBin.exe"
    if (Test-Path $exe) { $CertifyEdgeBin = $exe } else { throw "CertifyEdge not found: $CertifyEdgeBin" }
}
if (-not (Test-Path $CertifyEdgeSpec)) { throw "CertifyEdge spec not found: $CertifyEdgeSpec" }

Step "CertifyEdge: emit and verify TraceCertificate"
& $CertifyEdgeBin emit-pcs-certificate --spec $CertifyEdgeSpec --trace $TraceJson --out $CertJson
& $Pcs validate $CertJson
& $CertifyEdgeBin verify-certificate $CertJson --trace $TraceJson

Step "LabTrust-Gym: attach certificate"
& $Labtrust attach-certificate --bundle $PendingJson --certificate $CertJson --out $CertifiedJson
& $Pcs validate $CertifiedJson

$PfCmd = Get-Command $PfBin -ErrorAction SilentlyContinue
if (-not $PfCmd) { throw "Provability Fabric CLI not found: $PfBin" }

Step "Provability Fabric: verify and sign"
& $PfBin verify science-claim $CertifiedJson --out $VerificationJson
& $Pcs validate $VerificationJson
& $PfBin sign science-claim $CertifiedJson --out $SignedJson
& $Pcs validate $SignedJson
& $PfBin inspect science-claim $SignedJson

if (-not $SkipScientificMemory) {
    if (-not (Get-Command just -ErrorAction SilentlyContinue)) { throw "just not found (install just or use -SkipScientificMemory)" }
    if (-not (Test-Path (Join-Path $SmRoot "justfile"))) { throw "scientific-memory justfile not found: $SmRoot" }
    Step "Scientific Memory: import and render"
    Push-Location $SmRoot
    try {
        just pcs-import-bundle $SignedJson
        just pcs-render-claim $ClaimId
    } finally {
        Pop-Location
    }
}

Step "Validate chain artifacts"
& $Python (Join-Path $PSScriptRoot "verify_pcs_v01_chain.py") --work $Work --stage full

Write-Host ""
Write-Host "PCS v0.1 clean-checkout chain OK (workdir=$Work)"
