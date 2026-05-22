# Release-grade LabTrust reproducibility producer (Windows).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
if (-not $env:PCS_CORE) { $env:PCS_CORE = Join-Path (Split-Path $Root -Parent) "pcs-core" }
if (-not $env:PCS_BENCH) { $env:PCS_BENCH = Join-Path (Split-Path $Root -Parent) "pcs-bench" }
if (-not $env:BENCH_RUN_DIR) { $env:BENCH_RUN_DIR = "benchmark_runs/labtrust_reproducibility" }
python (Join-Path $Root "scripts/pcs_bench_producer.py") `
  --pcs-core $env:PCS_CORE `
  --pcs-bench $env:PCS_BENCH `
  --out $env:BENCH_RUN_DIR `
  @args
