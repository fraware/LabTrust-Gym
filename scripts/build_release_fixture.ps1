# Build the canonical release fixture for verify-release.
# Run from a known-good commit; then commit tests/fixtures/release_fixture_minimal/
# Usage: .\scripts\build_release_fixture.ps1 [-RepoRoot path]
# Env: SEED_BASE (default 100)

param([string]$RepoRoot)

$ErrorActionPreference = "Stop"
$RepoRoot = if ($RepoRoot) { (Resolve-Path $RepoRoot).Path } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
$SeedBase = if ($env:SEED_BASE) { $env:SEED_BASE } else { "100" }
$FixtureDir = Join-Path $RepoRoot (Join-Path "tests" (Join-Path "fixtures" "release_fixture_minimal"))

$env:LABTRUST_ALLOW_NETWORK = if ($env:LABTRUST_ALLOW_NETWORK) { $env:LABTRUST_ALLOW_NETWORK } else { "0" }

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path $FixtureDir | Out-Null

[string[]]$LabtrustCmd = if (Get-Command labtrust -ErrorAction SilentlyContinue) {
    "labtrust"
} else {
    "python", "-m", "labtrust_gym.cli.main"
}

function Run-Labtrust {
    param([string[]]$SubArgs)
    if ($LabtrustCmd.Length -eq 1) {
        & $LabtrustCmd[0] @SubArgs
    } else {
        $rest = $LabtrustCmd[1..($LabtrustCmd.Length-1)] + $SubArgs
        & $LabtrustCmd[0] @rest
    }
    if ($LASTEXITCODE -ne 0) { throw "labtrust failed with exit $LASTEXITCODE" }
}

Write-Host "=== 1/4 package-release (minimal) ==="
Run-Labtrust "package-release", "--profile", "minimal", "--seed-base", $SeedBase, "--out", $FixtureDir

Write-Host "=== 2/4 export-risk-register ==="
Run-Labtrust "export-risk-register", "--out", $FixtureDir, "--runs", $FixtureDir

Write-Host "=== 3/4 build-release-manifest ==="
Run-Labtrust "build-release-manifest", "--release-dir", $FixtureDir

Write-Host "=== 4/4 verify-release --strict-fingerprints ==="
Run-Labtrust "verify-release", "--release-dir", $FixtureDir, "--strict-fingerprints"

Write-Host "Release fixture built at $FixtureDir. Commit the minimal set needed for verify-release."
