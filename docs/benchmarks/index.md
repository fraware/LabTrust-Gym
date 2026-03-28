# Benchmarks and studies

Tasks, benchmark cards, official pack, studies, and reproduction.

## Tasks and cards

| Document | Description |
|----------|-------------|
| [Benchmarks](benchmarks.md) | Harness, tasks (A–H), metrics. |
| [Benchmark card](benchmark_card.md) | Scope, tasks, baselines. |
| [Coordination benchmark card](../coordination/coordination_benchmark_card.md) | Coord scale/risk (Task G/H). |
| [Evaluation checklist](evaluation_checklist.md) | Baseline status, when to regenerate, full command sequence. |
| [Scale and operational limits](scale_operational_limits.md) | Scale configs and limits. |
| [Throughput comparison](throughput_comparison.md) | Throughput-focused comparison (throughput_sla, scripted baseline). |
| [Prime Intellect Inference](prime_intellect_inference.md) | Env vars, CLI smoke, top-6 sweep, cross-provider. |
| [GCP Prime runner](gcp_prime_runner.md) | Compute Engine VM: install, background runs, fetch results. |
| [OpenHands SWE-bench with Prime](openhands_swebench_prime_runbook.md) | Minimal OpenHands SWE-bench runbook with Prime preflight checks. |
| [Hospital lab key metrics](hospital_lab_metrics.md) | Metrics that matter for hospital labs; SOTA leaderboard (main vs full), method-class comparison, run metadata, artifact paths, and coordination graphs in the UI bundle. |
| [Uncertainty quantification](uncertainty_quantification.md) | Epistemic vs aleatoric; metric mapping. |
| [Generalization and limits](../coordination/generalization_and_limits.md) | What was tested, what was not; comparison with other benchmarks. |

## Official pack and studies

| Document | Description |
|----------|-------------|
| [Official benchmark pack](official_benchmark_pack.md) | v0.1/v0.2 and run commands. |
| [Hospital lab full pipeline](hospital_lab_full_pipeline.md) | Full-pipeline script and orchestration. |
| [Hospital lab full pipeline results](hospital_lab_full_pipeline_results_report.md) | Example results report (regenerate runs as needed). |
| [Studies and plots](studies.md) | Study runner, make-plots. |
| [Coordination studies](../coordination/coordination_studies.md) | Coordination study runner and Pareto. |
| [LLM Coordination Protocol](llm_coordination_protocol.md) | LLM coordination protocol. |

## Reproducibility and paper

| Document | Description |
|----------|-------------|
| [Determinism contract](determinism_contract.md) | What the deterministic pipeline guarantees; RNG, canonical write, cross-version. |
| [Reproduce](reproduce.md) | Minimal results and figures. |
| [Paper claims](PAPER_CLAIMS.md) | Paper claims regression and snapshot. |
| [Paper provenance](paper/README.md) | Figures, tarball, commands. |
