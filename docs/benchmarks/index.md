# Benchmarks and studies

Tasks, benchmark cards, official pack, studies, and reproduction.

## Tasks and cards

| Document | Description |
|----------|-------------|
| [Benchmarks](benchmarks.md) | Harness, tasks (A–H), metrics. |
| [Benchmark card](benchmark_card.md) | Scope, tasks, baselines. |
| [Coordination benchmark card](../coordination/coordination_benchmark_card.md) | Coord scale/risk (Task G/H). |
| [Evaluation checklist](evaluation_checklist.md) | Baseline status, when to regenerate, full command sequence. |
| [Scientific credibility](scientific_credibility.md) | Program overview, non-goals, DoD checklist, LTG-PR1..PR9 map. |
| [Release runbook (LTG-PR9)](release_runbook.md) | Cut / verify engineering benchmark candidate; claim posture. |
| [Non-claims freeze (LTG-PR9)](non_claims_freeze.md) | Authoritative limitation block for release notes. |
| [External integrations](../agents/external_integrations.md) | LTG-PR7 pinned-release adapter gate (scripted / Gym / PZ / external / MARL / VA-13). |
| [Independent review (LTG-PR8)](../reviews/README.md) | Domain-review charter, protocol, unsigned slots, PR9 claim gate (not clinical validation). |
| [Golden suite governance](golden_suite_governance.md) | Per-scenario metadata, coverage gate, how to add scenarios, gap policy. |
| [Scale and operational limits](scale_operational_limits.md) | Scale configs and limits. |
| [Throughput comparison](throughput_comparison.md) | Throughput-focused comparison (throughput_sla, scripted baseline). |
| [Prime Intellect Inference](prime_intellect_inference.md) | Env vars, CLI smoke, top-6 sweep, cross-provider. |
| [GCP Prime runner](gcp_prime_runner.md) | Compute Engine VM: install, background runs, fetch results. |
| [OpenHands SWE-bench with Prime](openhands_swebench_prime_runbook.md) | Minimal OpenHands SWE-bench runbook with Prime preflight checks. |
| [Benchmark results pipeline](../benchmark_results_pipeline.md) | From coordination sweeps to presentation bundles. |
| [Hospital lab key metrics](hospital_lab_metrics.md) | Metrics that matter for hospital labs; SOTA leaderboard (main vs full), method-class comparison, run metadata, artifact paths, and coordination graphs in the UI bundle. |
| [Uncertainty quantification](uncertainty_quantification.md) | Epistemic vs aleatoric; metric mapping. |
| [Generalization and limits](../coordination/generalization_and_limits.md) | Tested scope, known limits, and comparison with other benchmarks. |

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
| [Determinism contract](determinism_contract.md) | Deterministic pipeline guarantee, RNG, canonical write, cross-version limits. |
| [Reproduce](reproduce.md) | Minimal results and figures. |
| [Paper claims](PAPER_CLAIMS.md) | Paper claims regression and snapshot. |
| [Paper provenance](paper/README.md) | Figures, tarball, commands. |
