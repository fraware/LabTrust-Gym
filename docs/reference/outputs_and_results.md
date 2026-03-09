# LabTrust-Gym: Outputs and Results Reference

This repo is **LabTrust-Gym**: a multi-agent environment (PettingZoo/Gym) for hospital lab automation, with a reference trust skeleton (RBAC, signed actions, audit log, invariants). The implemented workflow is a **blood sciences** lane (pathology lab); see [Glossary – Lab terminology](glossary.md#lab-terminology-hospital-lab-pathology-lab-blood-sciences-lab). Outputs are produced by the `labtrust` CLI, scripts, and CI; most go under a configurable output directory (default `labtrust_runs/` or `--out` / `--out-dir`).

---

## 1. Result types and where they live

| Category | Location / path pattern | Produced by | Pipeline |
|----------|--------------------------|-------------|----------|
| **Benchmark results** | `<out>/results.json` or `<out_dir>/results/<task>_<suffix>.json` | `run-benchmark`, `eval-agent`, `quick-eval`, `generate-official-baselines` | Any |
| **Episode logs** | `<out_dir>/logs/*.jsonl`, `episodes.jsonl` | Benchmark/study runs, quick-eval | Any |
| **Episode bundle** | `<run_dir>/episode_bundle.json` or `--out` path | `build-episode-bundle` | Any (for [episode viewer](episode_viewer.md)) |
| **Summaries** | `<out>/summary.md`, `<out>/summary.csv`, `summary_v0.2.csv`, `summary_v0.3.csv` | `quick-eval`, `summarize-results`, `generate-official-baselines` | Any. quick-eval: summary.md uses Violations (sum of violations_by_invariant_id), Blocked (sum of blocked_by_reason_code), plus seed, pipeline, results path. |
| **Coordination pack** | `<out>/pack_results/`, `pack_summary.csv`, `pack_gate.md`, `SECURITY/` | `run-coordination-security-pack`, `run-coordination-study` | Any (security pack: deterministic only) |
| **Study outputs** | `<out>/manifest.json`, `README.md` (minimal next-step hint), `results/<condition_id>/results.json`, `logs/<condition_id>/episodes.jsonl` | `run-study`, `run-coordination-study` | Any |
| **Coordination summaries** | `<out>/summary/sota_leaderboard.csv`, `sota_leaderboard.md`, `sota_leaderboard_full.csv`, `sota_leaderboard_full.md`, `method_class_comparison.csv`, `method_class_comparison.md` | `summarize-coordination`, `build-lab-coordination-report`, `run-coordination-study` | Any. Main leaderboard: key metrics + optional run metadata (seed_base, git_sha). Full leaderboard: all aggregated numerics. Method-class: same metrics by class (blocks_mean, attack_success_rate_mean included). **ui-export** includes these in the bundle as **coordination_artifacts** and generates **coordination/graphs/** HTML charts (SOTA key metrics, throughput, violations, resilience, method-class) when pack_summary is present. See [Hospital lab key metrics](../benchmarks/hospital_lab_metrics.md), [Frontend handoff](frontend_handoff_ui_bundle.md). |
| **Plots** | `<run>/figures/` (PNG/SVG), `data_tables/`, `RUN_REPORT.md` | `make-plots` | Any |
| **Security** | `<out>/SECURITY/attack_results.json`, `coordination_risk_matrix.md|csv` | `run-security-suite`, coordination security pack | Any |
| **Safety / risk** | `<out>/SAFETY_CASE/safety_case.json`, `safety_case.md`; `risk_register_out/RISK_REGISTER_BUNDLE.v0.1.json` | `safety-case`, `export-risk-register` | Any |
| **Evidence / release** | EvidenceBundle dirs, `RELEASE_MANIFEST.v0.1.json`, `receipts/`, `FIGURES/` | `export-receipts`, `verify-release`, `package-release`, `build-release-manifest` | Any |
| **Transparency** | `out/TRANSPARENCY_LOG/root.txt`, `log.json`, `proofs/` | CI (e.g. [CI](../operations/ci.md)) | Deterministic only |
| **PPO** | `labtrust_runs/ppo_out/model.zip` (or `LABTRUST_PPO_MODEL`) | `train-ppo` | Deterministic only (seeded) |
| **Build** | `dist/`, `build/` | `scripts/build_repro.sh`, setuptools; release workflow | — |
| **Docs** | `site/` | MkDocs (`mkdocs build`) | — |

Canonical baseline result files used for regression live in `benchmarks/baselines_official/v0.2/results/`.

---

## 1.1 Report artifacts (index)

| Report type | Typical path pattern | Produced by | Description |
|-------------|----------------------|-------------|-------------|
| Run summary | `<run_dir>/RUN_SUMMARY.md` | `make-plots` | What was run, output layout, next steps. Links are relative to the repository root. |
| Run report | `<run_dir>/figures/RUN_REPORT.md` | `make-plots` | Metric definitions, "which figure for which question" guide, figure list. Links are relative to the repository root. |
| Benchmark summary | `<out>/summary.csv`, `summary.md`, `summary_v0.2.csv`, `summary_v0.3.csv` | `summarize-results`, `generate-official-baselines` | Aggregates per task/baseline (mean, std; v0.3: quantiles, CI). |
| Study condition summary | `<run_dir>/figures/data_tables/summary.csv`, `paper_table.md` | `make-plots` | Per-condition aggregates for the study run. |
| Study figures | `<run_dir>/figures/*.png`, `*.svg`, `run_figures.pdf` | `make-plots` | Plots and data_tables for the study. |
| Determinism report | `<out>/determinism_report.md`, `determinism_report.json` | `run-determinism-report` | PASS/FAIL and hash comparison for two runs. |
| Coordination leaderboard | `<out>/summary/sota_leaderboard.csv`, `sota_leaderboard.md`, `method_class_comparison.*`, `summary/README.md` | `run-coordination-study`, `summarize-coordination` | SOTA and method-class aggregates; README.md describes the files and links to metrics. |
| Release notes | `<release_dir>/RELEASE_NOTES.md` | `package-release` | What ran, layout, result artifacts. |

Metric definitions: [Metrics contract](../contracts/metrics_contract.md).

---

## 1.2 Pipeline modes and result audit

Benchmarks run in exactly three **pipeline modes**: **deterministic** | **llm_offline** | **llm_live** (see [Pipelines in the README](https://github.com/fraware/LabTrust-Gym/blob/main/README.md#pipelines) and [Live LLM — Pipeline modes](../agents/llm_live.md#pipeline-modes) for canonical definitions).

- **deterministic** — Scripted agents only; no LLM interface. Default for CI, regression, and most CLI commands. Same seed yields same results; no network.
- **llm_offline** — LLM agent/coordination interface with a deterministic backend only (fixture lookup or seeded RNG). No network; reproducible given seed or fixtures.
- **llm_live** — Live LLM API (OpenAI, Ollama, etc.). Requires `--allow-network`; runs are non-deterministic and record `non_deterministic: true`.

**Result files always record pipeline and audit fields.** Every benchmark `results.json` (and thus summaries or studies built from it) includes **pipeline_mode**, **llm_backend_id**, **allow_network**, and **non_deterministic**. Consumers can tell deterministic vs LLM runs when inspecting any result file or UI export (e.g. `index.json`).

**Canonical baselines and regression.** The files under `benchmarks/baselines_official/v0.2/results/` are produced by **deterministic** runs only (`generate-official-baselines`). Regression and CI use deterministic pipelines; official baseline comparison is only valid against deterministic outputs.

---

## 2. Main result schemas and formats

- **Benchmark results**: `policy/schemas/results.v0.2.schema.json` (CI-stable), `policy/schemas/results.v0.3.schema.json` (paper-grade with quantiles/CI). Metrics (throughput, p95_turnaround_s, violations, blocked_by_reason_code, etc.) are defined in [metrics contract](../contracts/metrics_contract.md). The optional **metadata.llm_attribution_summary** (cost/latency per backend and agent) is only present when `LABTRUST_LLM_TRACE=1`; see [Observability — Attribution in results](observability.md#attribution-in-results).
- **Summaries**: `summary_v0.2.csv` (CI-stable aggregates), `summary_v0.3.csv` (adds quantiles/CI and uncertainty: containment_success_rate_ci_*, llm_confidence_ece_mean, llm_confidence_mce_mean), `summary.md` (markdown table + optional Run info). Coordination and pack outputs (`summary_coord.csv`, `pack_summary.csv`, `SECURITY/coordination_risk_matrix.*`) include sec.attack_success_rate_ci_*, sec.worst_case_attack_success_upper_95. See [Metrics contract](../contracts/metrics_contract.md) and [Uncertainty metrics in standard reports](../contracts/metrics_contract.md#uncertainty-metrics-in-standard-reports) for column semantics.
- **Risk/evidence**: `RISK_REGISTER_BUNDLE.v0.1.json`, EvidenceBundle v0.1, FHIR export; schemas under `policy/schemas/` and contracts under [contracts](../contracts/index.md).

---

## 3. CLI output contract

Every CLI command's exit code, minimal smoke args, and **expected output paths** are specified in [CLI output contract](../contracts/cli_contract.md). That table is the single source of truth for "what file(s) appear where" for each command; smoke tests in `tests/test_cli_smoke_matrix.py` assert these paths.

---

## 4. High-level flow of outputs

```mermaid
flowchart LR
  subgraph cli [CLI commands]
    quickEval[quick-eval]
    runBench[run-benchmark]
    runStudy[run-study]
    runPack[run-coordination-security-pack]
    summarize[summarize-results]
    makePlots[make-plots]
    exportRisk[export-risk-register]
    packageRelease[package-release]
  end
  subgraph out [Output dirs]
    resultsJSON[results.json / results/]
    logs[logs/*.jsonl]
    summaryMD[summary.md / summary.csv]
    packResults[pack_results/ pack_summary.csv]
    figures[figures/ RUN_REPORT.md]
    riskBundle[RISK_REGISTER_BUNDLE]
    releaseArtifact[MANIFEST receipts FIGURES]
  end
  quickEval --> resultsJSON
  quickEval --> logs
  quickEval --> summaryMD
  runBench --> resultsJSON
  runStudy --> resultsJSON
  runStudy --> logs
  runPack --> packResults
  summarize --> summaryMD
  makePlots --> figures
  exportRisk --> riskBundle
  packageRelease --> releaseArtifact
```

---

## 5. Quick reference: commands that write key outputs

| If you want... | Command(s) | Default pipeline |
|----------------|------------|------------------|
| Single benchmark result file | `run-benchmark --out <path>` (writes results.json) | deterministic |
| Quick run + markdown summary | `quick-eval` (writes under `labtrust_runs/quick_eval_*/`) | deterministic |
| Aggregated CSV/MD across runs | `summarize-results --in <dir_or_file> --out <dir>` | (consumes existing results) |
| Coordination SOTA / method comparison | `run-coordination-study`, `summarize-coordination` | deterministic (study: configurable) |
| Security attack results | `run-security-suite --out <dir>` | deterministic |
| Safety case + risk bundle | `safety-case --out <dir>`, `export-risk-register --out <dir>` | (no benchmark run) |
| Plots for a run | `make-plots --run <dir>` (prints figures/, RUN_REPORT.md, data_tables/, next: inspect RUN_REPORT; writes RUN_SUMMARY.md with See also links) | (consumes existing run) |
| One-line stats for a run directory (episodes, steps, violations, throughput) | `run-summary --run <dir>` (output: text or `--format json`) | (consumes existing run) |
| Full release artifact (paper-ready) | `package-release --profile paper_v0.1 --out <dir>` (prints RELEASE_NOTES.md and BENCHMARK_CARD.md for layout and result artifacts) | deterministic |
| Official baseline results | `generate-official-baselines --out <dir>` (e.g. `benchmarks/baselines_official/v0.2/`) | deterministic only |
| Episode bundle for viewer | `build-episode-bundle --run-dir <path> [--out <path>]` (writes episode_bundle.json) | (consumes existing run) |

All paths above are relative to CWD or the given `--out` / `--out-dir`; see [CLI output contract](../contracts/cli_contract.md) for exact filenames and schema references.

---

## 6. Recommended evaluation pipeline

- **Single run:** `run-benchmark --out <path>` then (optional) `run-summary --run <dir>` or `summarize-results --in <path> --out <dir>`.
- **Study:** `run-study --spec <spec> --out <dir>` then `make-plots --run <dir>`; read `RUN_SUMMARY.md` and `figures/RUN_REPORT.md`.
- **Quick check:** `quick-eval` then inspect `summary.md`; for more metrics run a full benchmark and `summarize-results`.
- **Coordination:** `run-coordination-study --spec <spec> --out <dir>` then see `summary/`; optionally run `summarize-coordination` if not already produced.

See [CLI output contract](../contracts/cli_contract.md) and [Studies](../benchmarks/studies.md) for command details and options.
