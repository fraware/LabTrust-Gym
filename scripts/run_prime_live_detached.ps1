<#
.SYNOPSIS
  Start run_all_methods_prime_live_full.py in a detached process (new console hidden).

.DESCRIPTION
  - Survives closing THIS PowerShell window (child keeps running).
  - Does NOT survive full shutdown, sleep, or hibernate — the OS stops the process.
  - For "PC is off" without paid CI: use a free-tier or homelab host (Oracle Always
    Free ARM, spare Pi/NUC, NAS SSH) and scripts/run_prime_live_nohup.sh over SSH.
    Optional paid/alternative: .github/workflows/prime-intellect-remote-dispatch.yml

  Logs go under runs/background_logs/. Load API key from .env yourself before calling,
  or rely on a persistent user/system env var.

.PARAMETER PassThru
  If set, prints the child process Id.

.EXAMPLE
  cd C:\Users\mateo\LabTrust-Gym
  .\scripts\run_prime_live_detached.ps1 -- --episodes 1 --methods llm_auction_bidder --out-dir runs/pi_bg
#>
[CmdletBinding()]
param(
    [switch] $PassThru
)

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $here "..")).Path
$logDir = Join-Path $repoRoot "runs\background_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logOut = Join-Path $logDir "prime_live_$stamp.out.log"
$logErr = Join-Path $logDir "prime_live_$stamp.err.log"
$metaPath = Join-Path $logDir "latest_prime_launch.json"

$py = $null
try { $py = (Get-Command python -ErrorAction Stop).Source } catch { }
if (-not $py) {
    try { $py = (Get-Command py -ErrorAction Stop).Source } catch { }
}
if (-not $py) {
    throw "python not found on PATH"
}

$scriptPath = Join-Path $repoRoot "scripts\run_all_methods_prime_live_full.py"
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Missing $scriptPath"
}

# Everything after '--' goes to the Python script (ArgumentList array).
$dash = [array]::IndexOf($args, "--")
if ($dash -ge 0) {
    $pyArgs = @($scriptPath) + $args[($dash + 1)..($args.Length - 1)]
} else {
    $pyArgs = @($scriptPath) + @($args)
}

$proc = Start-Process -FilePath $py `
    -ArgumentList $pyArgs `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError $logErr

$meta = @{
    started_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    pid            = $proc.Id
    repo_root      = $repoRoot
    python         = $py
    script_args    = ($pyArgs -join " ")
    stdout_log     = $logOut
    stderr_log     = $logErr
}
$meta | ConvertTo-Json -Depth 6 | Set-Content -Path $metaPath -Encoding UTF8

Write-Host "Detached Prime live run started."
Write-Host "  PID        $($proc.Id)"
Write-Host "  stdout     $logOut"
Write-Host "  stderr     $logErr"
Write-Host "  meta       $metaPath"
Write-Host ""
Write-Host "Tail logs: Get-Content -Wait -Path '$logOut' -Tail 30"

if ($PassThru) {
    $proc
}
