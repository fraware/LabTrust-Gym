# Shared helpers for PCS PowerShell scripts (dot-source from scripts in this folder).

function Get-PcsRepoRoot {
    # scripts/ -> pcs_qc_release/ -> examples/ -> repo root
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Get-PcsTool {
    param([Parameter(Mandatory = $true)][string]$Name)
    $Root = Get-PcsRepoRoot
    $venvExe = Join-Path $Root ".venv-pcs\Scripts\$Name.exe"
    if (Test-Path $venvExe) {
        return $venvExe
    }
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    throw @"
'$Name' not found. From the LabTrust-Gym repo root run:
  .\scripts\setup_pcs_dev.ps1
Then re-run this script, or activate .\.venv-pcs\Scripts\Activate.ps1

(Paths like .\scripts\setup_pcs_dev.ps1 only work when your shell cwd is the repo root, not examples/.)
"@
}
