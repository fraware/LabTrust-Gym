# Run all LLM-live tests and trials that use OPENAI_API_KEY. All should pass when the key is set.
# Per-role test skips unless ANTHROPIC_API_KEY is also set. Prompt-injection live test is included.
# Usage (PowerShell): $env:OPENAI_API_KEY='sk-...'; $env:LABTRUST_RUN_LLM_LIVE='1'; .\scripts\run_llm_live_coord_checks.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (-not $env:OPENAI_API_KEY) {
    Write-Error "OPENAI_API_KEY is not set. Set it to run live tests and trials."
    exit 1
}

$env:LABTRUST_RUN_LLM_LIVE = "1"

# 1) All live tests in test_openai_live.py (coord + agent path + two-episode + per-role). Per-role skips without ANTHROPIC_API_KEY.
Write-Host "`n=== 1/3 Live pytest: test_openai_live.py -m live (600s per test) ===`n"
python -m pytest tests/test_openai_live.py -m live -v --tb=short --timeout=600
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 2) Prompt-injection live test (openai_live schema valid and constrained)
Write-Host "`n=== 2/3 Live pytest: prompt-injection openai_live test ===`n"
python -m pytest tests/test_llm_prompt_injection_golden.py::test_openai_live_prompt_injection_schema_valid_and_constrained -v --tb=short --timeout=300
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 3) Trials script: all four coord methods, 1 episode each
Write-Host "`n=== 3/3 Trials script (all four methods, 1 episode) ===`n"
$outDir = "labtrust_runs/llm_coord_trials_openai"
python scripts/run_llm_coord_trials_openai.py --out-dir $outDir --episodes 1 --trace
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`nAll LLM-live commands completed successfully."
