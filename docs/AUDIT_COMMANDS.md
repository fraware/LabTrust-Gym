# Full audit: commands for a new user

Run these commands **in order** from the repo root to test everything, try everything, and fully audit the repo. Use PowerShell on Windows (no `&&`; use `;` or separate commands). When a command fails, note the output so we can fix errors; the goal is a state-of-the-art repo.

---

## Phase 1: Install and sanity check

From repo root (e.g. `C:\Users\mateo\LabTrust-Gym`). If the path contains accented characters, clone or move the repo to a path without them (see [installation.md](installation.md)).

```powershell
cd C:\Users\mateo\LabTrust-Gym
```

**1.1 Editable install (dev only)**  
May take 1–2 minutes.

```powershell
pip install -e ".[dev]"
```

**1.2 Version**

```powershell
labtrust --version
```

**1.3 Policy validation**

```powershell
labtrust validate-policy
```

Optional with partner overlay:

```powershell
labtrust validate-policy --partner hsl_like
```

---

## Phase 2: Lint and format

**2.1 Format (fix style)**  
Run once to fix formatting; then re-run the check in 2.2 to confirm.

```powershell
ruff format .
```

**2.2 Format check (CI-style)**

```powershell
ruff format --check .
```

**2.3 Lint**

```powershell
ruff check .
```

Fix any reported issues. To see only error codes and file:line:

```powershell
ruff check . --output-format concise
```

---

## Phase 3: Type checking

```powershell
mypy src/
```

---

## Phase 4: Core tests (no env/plots)

**4.1 Default test suite**  
Same as Makefile `test`: excludes PZ and benchmark smoke.

```powershell
pytest -q --ignore=tests/test_pz_parallel_smoke.py --ignore=tests/test_pz_aec_smoke.py --ignore=tests/test_benchmark_smoke.py
```

**4.2 Golden suite**  
Requires no PettingZoo. With placeholder adapter most scenarios are skipped unless `LABTRUST_RUN_GOLDEN=1`.

```powershell
pytest tests/test_golden_suite.py -q
```

Full golden suite (real engine; defines correctness):

```powershell
$env:LABTRUST_RUN_GOLDEN="1"; pytest tests/test_golden_suite.py -q
```

**4.3 Metamorphic properties (CI)**

```powershell
pytest tests/test_metamorphic_properties.py -q
```

---

## Phase 5: Install env + plots (benchmarks, quick-eval, reproduce)

```powershell
pip install -e ".[dev,env,plots]"
```

---

## Phase 6: Quick-eval and benchmark smoke

**6.1 Quick-eval (TaskA, TaskD, TaskE; 1 episode each)**

```powershell
labtrust quick-eval --seed 42 --out-dir ./labtrust_runs
```

**6.2 Benchmark smoke (1 episode per task)**

```powershell
labtrust bench-smoke --seed 42
```

Or via pytest:

```powershell
pytest tests/test_benchmark_smoke.py -v
```

**6.3 Single-task benchmark (smoke)**

```powershell
labtrust run-benchmark --task TaskA --episodes 2 --out .\runs\taska_smoke.json
```

Do not commit `results.json` or `*.json` at repo root; use `runs/` or `labtrust_runs/`.

---

## Phase 7: Baseline regression

Compares against official v0.2 baselines (CI guard).

```powershell
$env:LABTRUST_CHECK_BASELINES="1"; pytest tests/test_official_baselines_regression.py -v
```

---

## Phase 8: Coordination smoke

**8.1 Coordination tests**

```powershell
pytest tests/ -k "coordination" -q
```

**8.2 TaskG (scale, 1 episode)**

```powershell
labtrust run-benchmark --task TaskG_COORD_SCALE --episodes 1 --seed 42 --coord-method centralized_planner --out .\runs\taskg_smoke.json
```

**8.3 TaskH (risk injection, 1 episode)**

```powershell
labtrust run-benchmark --task TaskH_COORD_RISK --episodes 1 --seed 42 --coord-method market_auction --injection INJ-COLLUSION-001 --out .\runs\taskh_smoke.json
```

---

## Phase 9: Reproduce and package-release smoke

**9.1 Reproduce (minimal, smoke)**  
1 episode per condition.

```powershell
$env:LABTRUST_REPRO_SMOKE="1"; labtrust reproduce --profile minimal --out runs/repro_smoke
```

**9.2 Package-release determinism / paper smoke**  
Longer; run when you want to validate the full artifact pipeline.

```powershell
$env:LABTRUST_PAPER_SMOKE="1"; labtrust package-release --profile paper_v0.1 --seed-base 100 --out .\runs\paper_smoke
```

Then verify one evidence bundle (if present):

```powershell
# After package-release, locate first EvidenceBundle.v0.1 under the output dir, then:
labtrust verify-bundle --bundle .\runs\paper_smoke\<path-to-EvidenceBundle.v0.1>
```

Package-release pytest (includes paper_v0.1 smoke when env var set):

```powershell
$env:LABTRUST_PAPER_SMOKE="1"; pytest tests/test_package_release.py -v
```

---

## Phase 10: Transparency log (CI)

On Windows, create the artifact by hand then run the CLI. From repo root:

```powershell
New-Item -ItemType Directory -Force -Path artifact\_repr\TaskA
Set-Content -Path artifact\_repr\TaskA\results.json -Value '{"schema_version":"0.2","task":"TaskA","seeds":[42],"episodes":[{"seed":42,"metrics":{"throughput":5,"steps":100}}],"agent_baseline_id":"scripted_ops_v1"}'
Set-Content -Path artifact\_repr\TaskA\episodes.jsonl -Value '{"action_type":"CREATE_ACCESSION","t_s":10}'
labtrust transparency-log --in artifact --out out
# Check outputs exist:
Test-Path out\TRANSPARENCY_LOG\root.txt
Test-Path out\TRANSPARENCY_LOG\log.json
Test-Path out\TRANSPARENCY_LOG\proofs
```

---

## Phase 11: Docs build

```powershell
pip install -e ".[docs]"
mkdocs build --strict
```

---

## Phase 12: Optional extras

**MARL smoke** (requires `.[marl]`):

```powershell
pip install -e ".[dev,env,marl]"
$env:LABTRUST_MARL_SMOKE="1"; pytest tests/test_marl_smoke.py -v
```

**Security attack suite**:

```powershell
labtrust run-security-suite --smoke
```

**Safety case**:

```powershell
labtrust safety-case --out .\runs\safety_case
```

**Official pack (smoke)**:

```powershell
labtrust run-official-pack --out .\runs\official_pack --seed-base 42 --smoke
```

**Quickstart script (paper artifact)**  
Runs install, validate-policy, quick-eval, package-release paper_v0.1, verify-bundle:

```powershell
.\scripts\quickstart_paper_v0.1.ps1
```

---

## Phase 13: Full (real) runs

Use these when you need full test/benchmark coverage instead of smoke. Run after the corresponding smoke phase passes.

**13.1 Golden suite (real engine)**

```powershell
$env:LABTRUST_RUN_GOLDEN="1"; pytest tests/test_golden_suite.py -v
```

**13.2 Benchmark (multi-episode per task)**

```powershell
labtrust run-benchmark --task TaskA --episodes 10 --seed 42 --out .\runs\taska_full.json
labtrust run-benchmark --task TaskB --episodes 10 --seed 42 --out .\runs\taskb_full.json
labtrust run-benchmark --task TaskC --episodes 10 --seed 42 --out .\runs\taskc_full.json
labtrust run-benchmark --task TaskD --episodes 5 --seed 42 --out .\runs\taskd_full.json
labtrust run-benchmark --task TaskE --episodes 10 --seed 42 --out .\runs\taske_full.json
labtrust run-benchmark --task TaskF --episodes 5 --seed 42 --out .\runs\taskf_full.json
```

Or run all tasks via the official pack in full mode (see 13.6).

**13.3 Reproduce (full profile)**

```powershell
labtrust reproduce --profile full --out runs/repro_full --seed-base 100
```

**13.4 Package-release (full paper artifact)**

```powershell
labtrust package-release --profile paper_v0.1 --seed-base 100 --out .\runs\paper_full
```

Then verify a bundle:

```powershell
labtrust verify-bundle --bundle .\runs\paper_full\<path-to-EvidenceBundle.v0.1>
```

**13.5 Security attack suite (full)**

```powershell
labtrust run-security-suite --full --out runs/security_full
```

Or use default output dir:

```powershell
labtrust run-security-suite --full
```

**13.6 Official pack (full)**

```powershell
labtrust run-official-pack --out .\runs\official_pack_full --seed-base 42 --no-smoke
```

With full security suite inside the pack:

```powershell
labtrust run-official-pack --out .\runs\official_pack_full --seed-base 42 --no-smoke --full
```
 
**13.7 MARL**

```powershell
pip install -e ".[dev,env,marl]"
$env:LABTRUST_MARL_SMOKE="1"; pytest tests/test_marl_smoke.py -v
```

The MARL test is opt-in (LABTRUST_MARL_SMOKE=1) and runs a short PPO train/eval smoke. For a longer MARL run, use the same test; increase training steps only by changing the test or calling the training CLI directly if available.

**13.8 Coordination (TaskG / TaskH, more episodes)**

```powershell
labtrust run-benchmark --task TaskG_COORD_SCALE --episodes 5 --seed 42 --coord-method centralized_planner --out .\runs\taskg_full.json
labtrust run-benchmark --task TaskH_COORD_RISK --episodes 5 --seed 42 --coord-method market_auction --injection INJ-COLLUSION-001 --out .\runs\taskh_full.json
```

---

## Phase 14: Verify and export workflows

Ensures evidence-bundle verification, receipt export, FHIR export, UI export, and result summarization work end-to-end.

**14.1 Verify evidence bundle (fixture)**  
Use the repo fixture so this works without a prior package-release:

```powershell
labtrust verify-bundle --bundle .\ui_fixtures\evidence_bundle\EvidenceBundle.v0.1
```

**14.2 Verify a bundle from package-release (optional)**  
If you already ran Phase 13.4 (`paper_full`), find an EvidenceBundle under the output and verify it:

```powershell
# Find first EvidenceBundle.v0.1 under paper_full (PowerShell):
$bundle = (Get-ChildItem -Path .\runs\paper_full -Recurse -Directory -Filter "EvidenceBundle.v0.1" | Select-Object -First 1).FullName
if ($bundle) { labtrust verify-bundle --bundle $bundle }
```

**14.3 Export receipts and FHIR**  
Requires a reproduce run with episode logs. If you ran Phase 9.1 or 13.3, use that output; otherwise run a minimal reproduce first:

```powershell
# If you don't have runs/repro_smoke from Phase 9.1:
$env:LABTRUST_REPRO_SMOKE="1"; labtrust reproduce --profile minimal --out runs/repro_smoke
# Export receipts from one condition (adjust task/cond path if your repro layout differs):
labtrust export-receipts --run .\runs\repro_smoke\taska\logs\cond_0\episodes.jsonl --out .\runs\repro_smoke\taska\cond_0_export
# Export FHIR from that bundle:
labtrust export-fhir --receipts .\runs\repro_smoke\taska\cond_0_export\EvidenceBundle.v0.1 --out .\runs\repro_smoke\taska\cond_0_fhir
```

Check outputs: `runs\repro_smoke\taska\cond_0_export\EvidenceBundle.v0.1\` and `runs\repro_smoke\taska\cond_0_fhir\fhir_bundle.json`.

**14.4 UI export**  
Produce a UI-ready zip from a run directory (e.g. quick-eval or package-release output):

```powershell
# From quick-eval (run Phase 6.1 first if needed); use the timestamped dir under labtrust_runs:
labtrust ui-export --run .\labtrust_runs\quick_eval_<timestamp> --out .\runs\ui_bundle.zip
# Or from paper_full if available:
labtrust ui-export --run .\runs\paper_full --out .\runs\ui_bundle_from_paper.zip
```

**14.5 Summarize results**  
Aggregate one or more `results.json` files into summary CSV and markdown:

```powershell
labtrust summarize-results --in .\runs\taska_full.json .\runs\taskb_full.json --out .\runs\summary --basename summary
# Check: runs/summary/summary.csv and runs/summary/summary.md
```

---

## Phase 15: Study and plots

**15.1 Trust ablations study (smoke)**  
Runs a short study; requires `.[plots]` (Phase 5).

```powershell
$env:LABTRUST_REPRO_SMOKE="1"; labtrust run-study --spec policy/studies/trust_ablations.v0.1.yaml --out runs/trust_ablations_smoke
```

**15.2 Make plots**  
Generate figures from a study run:

```powershell
labtrust make-plots --run runs/trust_ablations_smoke
# Check: runs/trust_ablations_smoke/figures/
```

**15.3 Coordination study (smoke)**  
If you have a coordination study spec:

```powershell
labtrust run-coordination-study --spec tests/fixtures/coordination_study_smoke_spec.yaml --out runs/coord_study_smoke
```

---

## Phase 16: Full test sweep and remaining CLI

**16.1 Full pytest (all tests)**  
Run the full test suite. MARL smoke is excluded so it does not run (or time out) unless opted in; run it separately with `LABTRUST_MARL_SMOKE=1` (Phase 12/13).

```powershell
pytest -q --ignore=tests/test_pz_parallel_smoke.py --ignore=tests/test_pz_aec_smoke.py --ignore=tests/test_marl_smoke.py
```

To include PZ and benchmark smoke (requires `.[env]`), still exclude MARL to avoid timeout in default runs:

```powershell
pytest -q --ignore=tests/test_marl_smoke.py
```

(To use per-test timeouts, install `pytest-timeout` in the same env as pytest: `python -m pip install pytest-timeout`, then add `--timeout=120`.)

**16.2 Determinism report**  
Generate determinism report for a task (writes to `det_<task>/`):

```powershell
labtrust determinism-report --task TaskA --episodes 3 --seed 42 --out det_taska
# Check: det_taska/determinism_report.json and determinism_report.md
```

**16.3 Deps inventory**  
Emit runtime deps inventory (SBOM-like) to a directory:

```powershell
labtrust deps-inventory --out runs/deps_inventory
# Check: runs/deps_inventory/deps_inventory_runtime.json
```

---

## Phase 17: Optional (online, live LLM, baselines)

Use when you need to validate online mode, a live LLM backend, or baseline regeneration. Not required for the core audit.

**17.1 Serve (smoke)**  
Start the HTTP API (Ctrl+C to stop). In another shell you can hit health or run a short benchmark; see [online_mode.md](online_mode.md).

```powershell
labtrust serve --port 9000
```

**17.2 Live LLM (optional)**  
Requires API key or local Ollama; non-deterministic. See [llm_live.md](llm_live.md).

```powershell
# OpenAI (needs OPENAI_API_KEY):
# labtrust run-benchmark --task TaskA --episodes 2 --llm-backend openai_live --out .\runs\llm_openai.json
# Ollama (local):
# labtrust run-benchmark --task TaskA --episodes 2 --llm-backend ollama_live --out .\runs\llm_ollama.json
```

**17.3 Generate official baselines**  
Regenerate the official baseline results (v0.2). Used by maintainers; CI compares against these.

```powershell
# labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2 --seed-base 42
# Then run regression: $env:LABTRUST_CHECK_BASELINES="1"; pytest tests/test_official_baselines_regression.py -v
```

**17.4 MARL train/eval CLI**  
If `.[marl]` is installed and torch/SB3 work in your env:

```powershell
labtrust train-ppo --task TaskA --timesteps 2000 --seed 123 --out runs/ppo_smoke
labtrust eval-ppo --model runs/ppo_smoke/model.zip --episodes 3 --seed 123 --out runs/ppo_eval.json
```

---

## Summary order (copy-paste block)

Run in this order; stop at first failure and fix before continuing.

1. `pip install -e ".[dev]"`
2. `labtrust --version`
3. `labtrust validate-policy`
4. `ruff format .`
5. `ruff format --check .`
6. `ruff check .`
7. `mypy src/`
8. `pytest -q --ignore=tests/test_pz_parallel_smoke.py --ignore=tests/test_pz_aec_smoke.py --ignore=tests/test_benchmark_smoke.py`
9. `pytest tests/test_metamorphic_properties.py -q`
10. `pip install -e ".[dev,env,plots]"`
11. `labtrust quick-eval --seed 42 --out-dir ./labtrust_runs`
12. `labtrust bench-smoke --seed 42`
13. `$env:LABTRUST_CHECK_BASELINES="1"; pytest tests/test_official_baselines_regression.py -v`
14. `pytest tests/ -k "coordination" -q`
15. TaskG + TaskH commands (Phase 8.2, 8.3)
16. `$env:LABTRUST_REPRO_SMOKE="1"; labtrust reproduce --profile minimal --out runs/repro_smoke`
17. Transparency-log artifact + `labtrust transparency-log` (Phase 10)
18. `pip install -e ".[docs]"` then `mkdocs build --strict`

When something fails, capture the full command and the terminal output so we can fix errors and keep the repo state of the art.

---

## Summary: full audit (real runs)

Use this block when you want full (non-smoke) runs. Prerequisite: smoke audit above has passed.

1. `$env:LABTRUST_RUN_GOLDEN="1"; pytest tests/test_golden_suite.py -v`
2. `labtrust reproduce --profile full --out runs/repro_full --seed-base 100`
3. `labtrust package-release --profile paper_v0.1 --seed-base 100 --out .\runs\paper_full`
4. `labtrust run-security-suite --full --out runs/security_full`
5. `labtrust run-official-pack --out .\runs\official_pack_full --seed-base 42 --no-smoke`
6. TaskG/TaskH with more episodes (Phase 13.8) if needed

Optional: per-task benchmarks (Phase 13.2), MARL (13.7), and `labtrust verify-bundle` after package-release.
