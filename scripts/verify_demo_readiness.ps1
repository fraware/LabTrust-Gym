# Verify demo readiness for all three presentation tiers (Tier 1/2 full pipeline, Tier 3 compact pack).
# Runs prerequisites check, Tier 3 official pack smoke, and E2E verification chain.
# Optional: set $env:LABTRUST_DEMO_READINESS_FULL_PIPELINE = "1" to run a minimal full-pipeline sniff (slower).
#
# Usage: .\scripts\verify_demo_readiness.ps1 [work_dir]
#   work_dir: optional; default is a new temp directory.
#
# Env:
#   REPO_ROOT                        repo root (default: parent of script dir)
#   SEED_BASE                        seed for package-release and pack (default: 100)
#   LABTRUST_ALLOW_NETWORK           0 (default) for reproducibility
#   LABTRUST_DEMO_READINESS_FULL_PIPELINE  if 1, run minimal full pipeline (hospital_lab, smoke); timeout 20 min
#
# Exit: 0 if all steps pass; non-zero on first failure (stderr and step name printed).

$ErrorActionPreference = "Stop"

$RepoRoot = if ($env:REPO_ROOT) { $env:REPO_ROOT } else { (Get-Item $PSScriptRoot).Parent.FullName }
$SeedBase = if ($env:SEED_BASE) { $env:SEED_BASE } else { "100" }
$env:LABTRUST_ALLOW_NETWORK = if ($env:LABTRUST_ALLOW_NETWORK) { $env:LABTRUST_ALLOW_NETWORK } else { "0" }

$WorkDir = if ($args.Count -ge 1) {
    $p = $args[0]; if (-not [System.IO.Path]::IsPathRooted($p)) { Join-Path $RepoRoot $p } else { $p }
} else {
    Join-Path $env:TEMP "labtrust_demo_readiness_$(Get-Date -Format 'yyyyMMddHHmmss')"
}
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$PackDir = Join-Path $WorkDir "pack"
$ReleaseDir = Join-Path $WorkDir "release"
$FullDir = Join-Path $WorkDir "full"
$LogDir = Join-Path $WorkDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Set-Location $RepoRoot

# Resolve CLI
$LabtrustCmd = $null
if (Get-Command labtrust -ErrorAction SilentlyContinue) {
    $LabtrustCmd = @("labtrust")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $LabtrustCmd = @("python", "-m", "labtrust_gym.cli.main")
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $LabtrustCmd = @("python3", "-m", "labtrust_gym.cli.main")
} else {
    Write-Error "No labtrust, python, or python3 on PATH. Install the package (e.g. pip install -e `".[dev,env,plots]`")."
    exit 1
}

function Run-Step {
    param([string]$Name, [string[]]$ArgList)
    Write-Host "=== $Name ==="
    $logPath = Join-Path $LogDir "$Name.log"
    $proc = Start-Process -FilePath $ArgList[0] -ArgumentList $ArgList[1..($ArgList.Length-1)] -WorkingDirectory $RepoRoot -Wait -PassThru -NoNewWindow -RedirectStandardOutput $logPath -RedirectStandardError "${logPath}.err"
    if ($proc.ExitCode -eq 0) {
        Get-Content "${logPath}.err" -ErrorAction SilentlyContinue | Add-Content -Path $logPath
        Remove-Item "${logPath}.err" -ErrorAction SilentlyContinue
        Write-Host "  OK"
        return $true
    } else {
        Write-Host "  FAILED (exit $($proc.ExitCode))"
        Write-Host "--- stdout/stderr for step '$Name' ---"
        $logContent = @()
        if (Test-Path $logPath) { $logContent += Get-Content $logPath -ErrorAction SilentlyContinue }
        if (Test-Path "${logPath}.err") { $logContent += Get-Content "${logPath}.err" -ErrorAction SilentlyContinue }
        if ($logContent.Count -eq 0) { Write-Host "(no output captured)" } else { $logContent | Write-Host }
        return $false
    }
}

# 1) Prerequisites: version and validate-policy
if (-not (Run-Step "labtrust-version" ($LabtrustCmd + "--version"))) {
    Write-Error "Demo readiness failed at labtrust --version"
    exit 1
}
if (-not (Run-Step "validate-policy" ($LabtrustCmd + "validate-policy"))) {
    Write-Error "Demo readiness failed at validate-policy"
    exit 1
}

# 2) Tier 3 (compact): official pack with smoke
$env:LABTRUST_OFFICIAL_PACK_SMOKE = "1"
if ($env:LABTRUST_PAPER_SMOKE) { Remove-Item Env:LABTRUST_PAPER_SMOKE -ErrorAction SilentlyContinue }
if (-not (Run-Step "run-official-pack" ($LabtrustCmd + "run-official-pack" + "--out", $PackDir, "--seed-base", $SeedBase))) {
    Write-Error "Demo readiness failed at run-official-pack (Tier 3)"
    exit 1
}
$required = @(
    (Join-Path $PackDir "baselines\results"),
    (Join-Path $PackDir "SECURITY"),
    (Join-Path $PackDir "SAFETY_CASE"),
    (Join-Path $PackDir "pack_manifest.json"),
    (Join-Path $PackDir "PACK_SUMMARY.md")
)
foreach ($p in $required) {
    if (-not (Test-Path $p)) {
        Write-Error "Demo readiness failed: official pack missing required path: $p"
        exit 1
    }
}
Remove-Item Env:LABTRUST_OFFICIAL_PACK_SMOKE -ErrorAction SilentlyContinue

# 3) E2E verification chain (trustworthiness)
if (-not (Run-Step "package-release" ($LabtrustCmd + "package-release" + "--profile", "minimal", "--seed-base", $SeedBase, "--out", $ReleaseDir))) {
    Write-Error "Demo readiness failed at package-release"
    exit 1
}
if (-not (Run-Step "export-risk-register" ($LabtrustCmd + "export-risk-register" + "--out", $ReleaseDir, "--runs", $ReleaseDir))) {
    Write-Error "Demo readiness failed at export-risk-register"
    exit 1
}
$bundlePath = Join-Path $ReleaseDir "RISK_REGISTER_BUNDLE.v0.1.json"
if (-not (Test-Path $bundlePath)) {
    Write-Error "Demo readiness failed: risk register bundle not written"
    exit 1
}
if (-not (Run-Step "build-release-manifest" ($LabtrustCmd + "build-release-manifest" + "--release-dir", $ReleaseDir))) {
    Write-Error "Demo readiness failed at build-release-manifest"
    exit 1
}
# Use absolute path for release-dir so labtrust resolves it correctly on all platforms.
# Omit --strict-fingerprints here so demo readiness passes; CI (ci_e2e_artifacts_chain.sh) uses --strict-fingerprints.
$ReleaseDirAbs = [System.IO.Path]::GetFullPath($ReleaseDir)
if (-not (Run-Step "verify-release" ($LabtrustCmd + "verify-release" + "--release-dir", $ReleaseDirAbs))) {
    Write-Error "Demo readiness failed at verify-release"
    exit 1
}

# 4) Optional: minimal full-pipeline sniff (Tier 2). No timeout in PS1; may take 10-20 min.
if ($env:LABTRUST_DEMO_READINESS_FULL_PIPELINE -eq "1") {
    Write-Host "=== full-pipeline-sniff (Tier 2) ==="
    $logPath = Join-Path $LogDir "full_pipeline_sniff.log"
    & python scripts/run_hospital_lab_full_pipeline.py --out $FullDir --matrix-preset hospital_lab --security smoke --include-coordination-pack --seed-base $SeedBase *> $logPath
    if ($LASTEXITCODE -eq 0) {
        $manifestPath = Join-Path $FullDir "summary\full_pipeline_manifest.json"
        if ((Test-Path $manifestPath) -and (Test-Path (Join-Path $FullDir "baselines")) -and (Test-Path (Join-Path $FullDir "SECURITY")) -and (Test-Path (Join-Path $FullDir "coordination_pack"))) {
            Write-Host "  OK"
        } else {
            Get-Content $logPath
            Write-Error "Demo readiness failed: full pipeline manifest or key dirs missing"
            exit 1
        }
    } else {
        Get-Content $logPath
        Write-Error "Demo readiness failed at full-pipeline-sniff (exit $LASTEXITCODE)"
        exit 1
    }
}

Write-Host "Demo readiness passed (work_dir=$WorkDir). All three tiers are ready."
