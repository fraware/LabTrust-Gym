# Run the coordination security pack on a remote server so it keeps running when your PC is off.
# No password prompt: uses SSH (key or agent). One-time setup on the server: clone repo, install deps.
#
# Server setup (once, on the remote machine):
#   git clone <this-repo-url> LabTrust-Gym && cd LabTrust-Gym && pip install -e ".[dev,env,plots]"
#
# From your PC (PowerShell):
#   .\scripts\run_pack_on_remote_server.ps1 -RemoteHost my-server.example.com
#   .\scripts\run_pack_on_remote_server.ps1 -RemoteHost my-server.example.com -User ubuntu -RemotePath /home/ubuntu/LabTrust-Gym
#   .\scripts\run_pack_on_remote_server.ps1 -RemoteHost 10.0.0.5 -Background -Workers 16
#
# -Background: run in background on the server (nohup) so you can close the SSH session; output in pack_run.log on the server.

param(
    [Parameter(Mandatory = $true)]
    [string] $RemoteHost,
    [string] $User = "",
    [string] $RemotePath = "~/LabTrust-Gym",
    [string] $KeyPath = "",
    [int] $Workers = 16,
    [string] $OutDir = "pack_run_full_matrix",
    [switch] $Background
)

$ErrorActionPreference = "Stop"

$sshTarget = if ($User) { "$User@$RemoteHost" } else { $RemoteHost }
$sshArgs = @()
if ($KeyPath) {
    if (-not (Test-Path -LiteralPath $KeyPath)) { Write-Host "Key file not found: $KeyPath" -ForegroundColor Red; exit 1 }
    $sshArgs += "-i", $KeyPath
}

# Remote command: run pack (out dir relative to RemotePath after cd)
$packCmd = "python -m labtrust_gym.cli.main run-coordination-security-pack --out `"$OutDir`" --matrix-preset full_matrix --seed 42 --workers $Workers"
$remoteCmd = "cd $RemotePath && $packCmd"

if ($Background) {
    $logFile = "pack_run.log"
    $remoteCmd = "cd $RemotePath && nohup $packCmd > $logFile 2>&1 & echo Started in background. Log: $RemotePath/$logFile"
}

Write-Host "Running pack on $sshTarget (path: $RemotePath, workers: $Workers)..." -ForegroundColor Cyan
if ($Background) { Write-Host "Background mode: run will continue after you disconnect. Log on server: $RemotePath/$logFile" -ForegroundColor Cyan }

& ssh @sshArgs $sshTarget $remoteCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "Remote run failed (exit code $LASTEXITCODE). Check SSH access and that the repo is at $RemotePath with dependencies installed." -ForegroundColor Red
    exit $LASTEXITCODE
}

if (-not $Background) {
    Write-Host "Pack run finished on server. Output directory on server: $RemotePath/$OutDir" -ForegroundColor Green
} else {
    Write-Host "Pack started in background on server. To watch log: ssh $sshTarget tail -f $RemotePath/$logFile" -ForegroundColor Green
}
