# Build viewer-data compatible layout under demo_video_out for Lovable portal.
# Creates demo_video_out/viewer_data_latest/ with latest.json and RISK_REGISTER_BUNDLE.v0.1.json
# so the portal can load "latest" when this folder is served (e.g. http://localhost:8080/).
#
# Usage: from repo root, .\demo_video_out\build_viewer_data_latest.ps1
# Requires: demo_video_out/risk_out/RISK_REGISTER_BUNDLE.v0.1.json (from export-risk-register)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LatestDir = Join-Path $ScriptDir "viewer_data_latest"
$RiskOut = Join-Path $ScriptDir "risk_out"
$BundleSrc = Join-Path $RiskOut "RISK_REGISTER_BUNDLE.v0.1.json"

if (-not (Test-Path $BundleSrc)) {
    Write-Error "Risk register bundle not found: $BundleSrc. Run export-risk-register first."
    exit 1
}

New-Item -ItemType Directory -Force -Path $LatestDir | Out-Null
Copy-Item -Path $BundleSrc -Destination (Join-Path $LatestDir "RISK_REGISTER_BUNDLE.v0.1.json") -Force

$GitSha = ""
if (Get-Command git -ErrorAction SilentlyContinue) {
    $GitSha = (git rev-parse HEAD 2>$null) -replace "`n", ""
}
try {
    $Version = (python -c "import importlib.metadata; print(importlib.metadata.version('labtrust-gym'))" 2>$null)
} catch {
    $Version = "0.1.0"
}
$GeneratedAt = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")

$LatestJson = @{
    git_sha       = $GitSha
    version       = $Version
    generated_at  = $GeneratedAt
    bundle_file   = "RISK_REGISTER_BUNDLE.v0.1.json"
} | ConvertTo-Json

$LatestJson | Set-Content -Path (Join-Path $LatestDir "latest.json") -Encoding UTF8 -NoNewline

Write-Host "Viewer-data layout built at $LatestDir (latest.json + RISK_REGISTER_BUNDLE.v0.1.json)."
Write-Host "Serve this folder (e.g. npx serve $LatestDir -p 8080) and set VITE_DATA_BASE_URL to http://localhost:8080/"
