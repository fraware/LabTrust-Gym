# Run the live OpenAI integration test (one episode TaskA).
# Requires: OPENAI_API_KEY set in the environment (or pass as first argument for this run only).
# Usage:
#   .\scripts\run_live_llm_integration.ps1
#   $env:OPENAI_API_KEY = "sk-..."; .\scripts\run_live_llm_integration.ps1
$ErrorActionPreference = "Stop"
if ($args.Count -ge 1) {
    $env:OPENAI_API_KEY = $args[0]
}
if (-not $env:OPENAI_API_KEY) {
    Write-Host "OPENAI_API_KEY is not set. Set it and re-run, or pass it as the first argument:"
    Write-Host "  `$env:OPENAI_API_KEY = 'sk-...'; .\scripts\run_live_llm_integration.ps1"
    Write-Host "  .\scripts\run_live_llm_integration.ps1 sk-..."
    exit 1
}
$env:LABTRUST_RUN_LLM_LIVE = "1"
$env:LABTRUST_ALLOW_NETWORK = "1"
Push-Location $PSScriptRoot\..
try {
    python -m pytest tests/test_openai_live.py::test_openai_live_one_episode_task_a -v --tb=short
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
