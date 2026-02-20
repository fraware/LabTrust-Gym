# Run the coordination security pack: either in this terminal (-RunNow) or as a scheduled task (default).
# Default 8 workers to avoid overloading the machine; use -Workers 4 if it still struggles, or raise for more speed.
# Usage:
#   .\scripts\run_pack_scheduled_task.ps1 -RunNow
#   .\scripts\run_pack_scheduled_task.ps1 -RunNow -Workers 4
#   .\scripts\run_pack_scheduled_task.ps1 -Workers 8

param(
    [int] $Workers = 8,
    [switch] $RunNow,
    [string] $TaskName = "LabTrustPackRun",
    [string] $OutDir = ""
)

$ErrorActionPreference = "Stop"
# ProcessPoolExecutor on Windows allows max_workers <= 61
$Workers = [Math]::Min(61, [Math]::Max(1, $Workers))
$RepoRoot = if ($env:REPO_ROOT) { $env:REPO_ROOT } else { (Get-Item $PSScriptRoot).Parent.FullName }
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot "pack_run_full_matrix" }

$PythonExe = (Get-Command python -ErrorAction Stop).Source
$PackArgs = "run-coordination-security-pack --out `"$OutDir`" --matrix-preset full_matrix --seed 42 --workers $Workers"
$FullArgs = "-m labtrust_gym.cli.main $PackArgs"
$LogFile = Join-Path $RepoRoot "pack_run.log"

if ($RunNow) {
    Write-Host "Running pack in this terminal (Workers: $Workers, Out: $OutDir) ..."
    Push-Location $RepoRoot
    try {
        & $PythonExe -m labtrust_gym.cli.main run-coordination-security-pack --out $OutDir --matrix-preset full_matrix --seed 42 --workers $Workers
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

# Redirect pack output to a log file so you can watch with: Get-Content pack_run.log -Wait -Tail 30
$CmdArg = "/c `"cd /d \`"$RepoRoot\`" && \`"$PythonExe\`" -m labtrust_gym.cli.main run-coordination-security-pack --out \`"$OutDir\`" --matrix-preset full_matrix --seed 42 --workers $Workers > \`"$LogFile\`" 2>&1`""
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $CmdArg -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -ErrorAction Stop | Out-Null
Write-Host "Task '$TaskName' registered. It will run in 1 minute (runs while you are logged on; lock the PC to keep it running)."
Write-Host "Output directory: $OutDir"
Write-Host "Workers: $Workers"
Write-Host "Log file: $LogFile"
Write-Host "To watch progress live: Get-Content '$LogFile' -Wait -Tail 30"
Write-Host "To run the task now: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To view task: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove task: Unregister-ScheduledTask -TaskName '$TaskName'"
