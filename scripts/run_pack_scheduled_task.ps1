# Register a scheduled task to run the coordination security pack (no password).
# The task runs when you are logged on. To run when your PC is off, use run_pack_on_remote_server.ps1.
# Run from repo root or set REPO_ROOT. Usage:
#   .\scripts\run_pack_scheduled_task.ps1
#   .\scripts\run_pack_scheduled_task.ps1 -Workers 16

param(
    [int] $Workers = 16,
    [string] $TaskName = "LabTrustPackRun",
    [string] $OutDir = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = if ($env:REPO_ROOT) { $env:REPO_ROOT } else { (Get-Item $PSScriptRoot).Parent.FullName }
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "pack_run_full_matrix" }

$PythonExe = (Get-Command python -ErrorAction Stop).Source
$PackArgs = "run-coordination-security-pack --out `"$OutDir`" --matrix-preset full_matrix --seed 42 --workers $Workers"
$FullArgs = "-m labtrust_gym.cli.main $PackArgs"

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $FullArgs -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -ErrorAction Stop | Out-Null
} catch {
    Write-Host "Failed to register task: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "Task '$TaskName' registered. It will run in 1 minute (while you stay logged on)."
Write-Host "Output directory: $OutDir"
Write-Host "Workers: $Workers"
Write-Host "To run the task now: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To view task: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove task: Unregister-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To run the pack when your PC is off, use: .\scripts\run_pack_on_remote_server.ps1 -Host <your-server>"
