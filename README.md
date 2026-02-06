# LabTrust-Gym

A multi-agent environment (PettingZoo/Gym style) for a self-driving hospital lab, with a reference trust skeleton: RBAC, signed actions, append-only audit log, invariants, and anomaly throttles.

## North star

- **Environment**: Pip-installable, standard multi-agent API (PettingZoo AEC or parallel).
- **Trust skeleton**: Roles/permissions, signed actions, hash-chained audit log, invariants, reason codes.
- **Benchmarks**: Tasks and baselines (scripted, MARL, LLM) with clear safety/throughput trade-offs.

## Principles

- **Golden scenarios drive development**: The simulator is correct when the golden suite passes.
- **Policy is data**: Invariants, tokens, reason codes, catalogue, zones live in versioned files under `policy/`.
- **Determinism**: Golden runs are deterministic (seeded RNG, no ambient randomness).
- **No silent failure**: Missing hooks or invalid data fail loudly with reason codes.

## Installation (pip)

From PyPI (env + plots for benchmarks and quick-eval):

```bash
pip install labtrust-gym[env,plots]
labtrust --version
labtrust quick-eval
```

Quick-eval runs 1 episode each of TaskA, TaskD, and TaskE with scripted baselines, prints a markdown summary, and stores logs under `./labtrust_runs/`.

From source (development):

```bash
git clone https://github.com/fraware/LabTrust-Gym.git
cd LabTrust-Gym
pip install -e ".[dev]"
labtrust validate-policy
pytest -q
```

For benchmarks, studies, and plots (PettingZoo + matplotlib):

```bash
pip install -e ".[dev,env,plots]"
labtrust run-benchmark --task TaskA --episodes 5 --out results.json
labtrust reproduce --profile minimal
```

Optional extras: `.[env]` (PettingZoo/Gymnasium), `.[plots]` (matplotlib), `.[marl]` (Stable-Baselines3), `.[docs]` (MkDocs + mkdocstrings).

## Pipelines

Benchmarks run in one of three pipeline modes. Defaults are **offline** (no network, no API cost).

| Mode | Network | Agents | Use case |
|------|---------|--------|----------|
| **deterministic** | No | Scripted only | CI, regression, reproduce, paper artifact (default) |
| **llm_offline** | No | LLM interface, deterministic backend only | Offline LLM evaluation, no API calls |
| **llm_live** | Yes (opt-in) | Live OpenAI/Ollama | Interactive or cost-accepting runs; requires `--allow-network` |

Set mode with `--pipeline-mode`; for live LLM also pass `--allow-network` or `LABTRUST_ALLOW_NETWORK=1`. See [docs/llm_live.md](docs/llm_live.md) and [docs/installation.md](docs/installation.md#configuration-no-env-file-required).

### Why you saw no OpenAI calls

Runs are **offline by default**. If you expected OpenAI (or another live LLM) to be called and saw none:

- **quick-eval**, **run-benchmark**, **reproduce**, and **package-release** use `pipeline_mode=deterministic` unless you pass `--pipeline-mode llm_live` and `--allow-network`.
- No `.env` or `OPENAI_API_KEY` is read for making calls unless the pipeline is **llm_live** and network is allowed.
- To run with a live LLM: `--pipeline-mode llm_live --allow-network --llm-backend openai_live` (or `ollama_live`). The CLI will print a red warning: **WILL MAKE NETWORK CALLS / MAY INCUR COST**.

Every run records which pipeline was used: **results.json** (and UI export **index.json**) include `pipeline_mode`, `llm_backend_id`, `llm_model_id`, and `allow_network` so a reviewer can tell at a glance whether a run was live-LLM or deterministic.

## Quick eval

After `pip install labtrust-gym[env,plots]`, run a minimal sanity check (1 episode each of TaskA, TaskD, TaskE):

```bash
labtrust quick-eval
```

Output: a markdown summary (throughput, violations, blocked counts) and logs under `./labtrust_runs/quick_eval_<timestamp>/`. Use `--seed` and `--out-dir` to customize.

## CLI

- **validate-policy** — Validate all policy YAML/JSON against schemas.
- **quick-eval** — 1 episode each of TaskA, TaskD, TaskE; markdown summary and logs under `./labtrust_runs/` (`--seed`, `--out-dir`).
- **run-benchmark** — Run TaskA, TaskB, TaskC, TaskD, TaskE, or TaskF; write results.json (`--task`, `--episodes`, `--out`). Optional `--llm-backend {deterministic,openai_live,ollama_live}` to use LLM agent; optional `--llm-agents` to restrict which agents use the LLM (default: scripted agents). See [docs/llm_live.md](docs/llm_live.md).
- **eval-agent** — Run benchmark with an external agent (module:Class or module:function); write results.json (v0.2). Example: `--agent "examples.external_agent_demo:SafeNoOpAgent"` (`--task`, `--episodes`, `--out`, `--seed`, `--partner`, `--timing`).
- **bench-smoke** — 1 episode per task (TaskA, TaskB, TaskC).
- **export-receipts** — Export Receipt.v0.1 and EvidenceBundle.v0.1 from episode log (`--run`, `--out`).
- **export-fhir** — Export FHIR R4 Bundle from receipts dir (`--receipts`, `--out`).
- **verify-bundle** — Verify EvidenceBundle.v0.1: manifest integrity, schema, hashchain, invariant trace; optional policy fingerprints (tool_registry, rbac, coordination, memory) when present in manifest (`--bundle`, `--allow-extra-files`).
- **run-security-suite** — Run security attack suite (smoke or full); emit SECURITY/attack_results.json and securitization packet (coverage, reason_codes, deps_inventory). See [docs/security_attack_suite.md](docs/security_attack_suite.md).
- **safety-case** — Generate safety case (claim to control, test, artifact, verification command) to SAFETY_CASE/safety_case.json and safety_case.md (`--out`). See [docs/implementation_verification.md](docs/implementation_verification.md).
- **run-official-pack** — Run the Official Benchmark Pack v0.1 (tasks, scales, baselines, coordination methods, security suite, safety case, transparency log); single output dir for external researchers (`--out`, `--seed-base`, `--smoke`/`--no-smoke`, `--full`). See [docs/official_benchmark_pack.md](docs/official_benchmark_pack.md).
- **ui-export** — Export UI-ready zip (index, events, receipts_index, reason_codes) from a run dir (`--run`, `--out`). UI consumes this as primary input; see [docs/ui_data_contract.md](docs/ui_data_contract.md).
- **run-study** — Run study from spec (`--spec`, `--out`); ablations → conditions → results.
- **run-coordination-study** — Run coordination study (scale × method × injection); writes cells, summary_coord.csv, pareto.md (`--spec`, `--out`). See [Coordination studies](docs/coordination_studies.md).
- **make-plots** — Generate figures and data tables from a study run (`--run`); for coordination runs adds resilience vs p95_tat and attack_success_rate bar.
- **reproduce** — Reproduce minimal results + figures: TaskA & TaskC sweep + plots (`--profile minimal | full`, optional `--out`, `--seed-base`).
- **package-release** — Release candidate artifact: reproduce + receipts + FHIR + plots + MANIFEST + BENCHMARK_CARD + summary table (`--profile minimal | full | paper_v0.1`, `--out`, optional `--seed-base`, `--keep-repro`). Use **paper_v0.1** for a benchmark-first, paper-ready artifact (baselines + TaskF study + summarize + receipts + FIGURES/TABLES + **SECURITY/** attack suite and securitization packet + **SAFETY_CASE/** safety case + COORDINATION_CARD and frozen _coordination_policy); see [docs/paper_ready.md](docs/paper_ready.md).
- **generate-official-baselines** — Run Tasks A–F with official baselines; write results/, summary.csv, summary.md, metadata.json (`--out`, `--episodes`, `--seed`, `--timing`, `--partner`, `--force`). Registry: `benchmarks/baseline_registry.v0.1.yaml`.
- **summarize-results** — Load results.json from dir(s)/file(s), aggregate by task+baseline+partner_id; write **summary_v0.2.csv** (CI-stable), **summary_v0.3.csv** (paper-grade: quantiles, 95% CI), **summary.csv** (copy of v0.2), and summary.md (`--in`, `--out`, `--basename`). See [docs/metrics_contract.md](docs/metrics_contract.md). Compare to official baselines in `benchmarks/baselines_official/v0.1/` (or regenerate v0.2 with generate-official-baselines).
- **determinism-report** — Run benchmark twice with identical args in fresh temp dirs; write **determinism_report.md** and **determinism_report.json** (sha256 of episode logs, results.json, receipts bundle root hash); assert v0.2 metrics and episode log hash identical (`--task`, `--episodes`, `--seed`, `--out`, optional `--partner`, `--timing explicit|simulated`). With `--timing simulated`, device service-time sampling is seeded only from `--seed`.
- **train-ppo**, **eval-ppo** — PPO training/eval (requires `.[marl]`).
- **serve** — Start online HTTP server (optional auth, rate limits, B007 roles; GET /v0/summary returns summary view, GET /v0/episode-log admin-only). See [docs/security_online.md](docs/security_online.md), [docs/output_controls.md](docs/output_controls.md), [docs/deployment_hardening.md](docs/deployment_hardening.md).

## Repository structure

Keep the repo root minimal. Put CLI outputs in `labtrust_runs/` or a path given by `--out`; do not commit `results.json`, `out.json`, or other artifacts at root (see [Repository structure](docs/repository_structure.md)).

| Path | Description |
|------|-------------|
| **policy/** | Versioned YAML/JSON: `schemas/`, `emits/`, `invariants/` (registry v1.0), `tokens/`, `reason_codes/`, `zones/`, `sites/`, `catalogue/`, `stability/`, `equipment/`, `critical/`, `enforcement/`, `studies/`, `risks/` (risk_registry), `coordination/` (methods, method_risk_matrix, coordination_study_spec, injections.v0.2), `safety_case/` (claims.v0.1), `official/` (benchmark_pack.v0.1), `llm/`, `golden/` (golden_scenarios, prompt_injection_scenarios, security_attack_suite), `partners/`. Validated by `labtrust validate-policy`. |
| **src/labtrust_gym/** | Package: `config`, `engine/` (core_env, audit_log, zones, specimens, qc, critical, queueing, devices, signatures, rbac, transport, invariants, enforcement), `envs/` (PettingZoo), `baselines/` (scripted, adversary, llm, **coordination** (interface, methods, registry, **adversary_coord**), marl), `benchmarks/` (tasks TaskA–TaskH, runner, coordination_scale, metrics, summarize, **security_runner**, **securitization**, **official_pack**), `policy/` (loader, validate, risks, coordination, prompt_registry), `security/` (risk_injections, secret_scrubber, fs_safety, output_shaping, adversarial_detection, **safety_case**), `studies/` (study_runner, **coordination_study_runner**, plots, reproduce, package_release), `export/`, `online/`, `runner/`, `logging/`, `cli/`. |
| **tests/** | Pytest: golden suite, policy validation, benchmarks, **coordination** (scale, methods, study, policy), **risk_injections**, studies, export, online, etc. |
| **benchmarks/** | Baseline registry, official baselines (v0.1, v0.2). |
| **examples/** | Example agents (external_agent_demo, scripted_ops_agent, llm_agent_mock_demo, etc.). |
| **docs/** | MkDocs source: architecture, benchmarks, coordination (methods, scale, studies, policy, checklist), contracts, installation, STATUS, security, LLM, MARL. |
| **scripts/** | Quickstart and paper-release scripts. |
| **ui_fixtures/** | Minimal results, episode log, evidence bundle for offline UI work. |

## Golden runner

The golden runner (`labtrust_gym.runner`) runs scenario scripts from `policy/golden/golden_scenarios.v0.1.yaml` against an environment adapter. The adapter must implement `LabTrustEnvAdapter` (reset, step, query). Step results must conform to the runner output contract (status, emits, violations, hashchain, etc.). Unknown emits fail the suite. With the real engine the full golden suite passes: `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py`.

## Reproducibility and citation

- **Reproduce**: `labtrust reproduce --profile minimal` (see [docs/reproduce.md](docs/reproduce.md)).
- **Release artifact**: `labtrust package-release --profile minimal --out /tmp/labtrust_release` produces MANIFEST.v0.1.json (file hashes), BENCHMARK_CARD.md, metadata.json, results (v0.2 schema), summary.csv/summary.md (leaderboard table), plots, receipts, and FHIR bundles. Use `--seed-base N` for deterministic runs. For a **paper-ready** artifact (baselines + TaskF study + FIGURES/TABLES + receipts + **SECURITY/** attack suite and securitization packet + **COORDINATION_CARD.md** and frozen **\_coordination_policy/**): `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>` (see [docs/paper_ready.md](docs/paper_ready.md), [docs/security_attack_suite.md](docs/security_attack_suite.md), [docs/coordination_benchmark_card.md](docs/coordination_benchmark_card.md)).
- **Official baselines**: **v0.2 is canonical.** Frozen results and summary table are in `benchmarks/baselines_official/v0.2/` (see [Benchmark card](docs/benchmark_card.md)). Baseline regression compares against v0.2; v0.1 is legacy. Regenerate with `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force` (matches CI). Compare: `labtrust summarize-results --in benchmarks/baselines_official/v0.2/results/ your_results.json --out /tmp/compare`.
- **How to cite**: This project uses [CITATION.cff](CITATION.cff). You can use [citation-file-format](https://citation-file-format.github.io/) tooling or cite the repository: *LabTrust-Gym: a multi-agent environment for a self-driving hospital lab with a trust skeleton*. https://github.com/fraware/LabTrust-Gym.

## Improvements before going online

Before adding online APIs and non-deterministic runs, see **[docs/IMPROVEMENTS_BEFORE_ONLINE.md](docs/IMPROVEMENTS_BEFORE_ONLINE.md)** for a checklist: stability (ui_fixtures, long tests), **code optimization** (policy loading in hot path, large JSONL, summarize/export), testing (pytest timeout, coverage, CI), documentation, and pre-online readiness.

## Current state

See **docs/STATUS.md** for a detailed report: policy validation, hashchain, tokens, zones, specimens, QC, critical results (v0.2 escalation ladder), catalogue/stability, co-location, queueing, invariant registry, enforcement, **transport** (multi-site), **export** (receipts, FHIR R4), **package-release**, **security** (B008 deployment hardening, B009 output controls, **security attack suite** and securitization packet, coordination identity, tool sandbox, memory hardening, **safety case generator**), **coordination red team** (TaskH injections v0.2, adversary strategies, stealth/attribution/blast-radius metrics), **Official Benchmark Pack v0.1** (`labtrust run-official-pack`), **online serve** (auth, rate limits, summary/episode-log endpoints), PettingZoo wrappers, scripted/adversary/LLM/MARL baselines, TaskA–TaskH, **quick-eval**, PyPI packaging (`labtrust --version`), studies (run-study, make-plots, reproduce, package-release), and docs site (MkDocs + API reference).

## v0.1.0 release and contract freeze

- **Version:** `labtrust --version` prints v0.1.0 + git SHA. Tag **v0.1.0** from a clean main commit for release.
- **Contract freeze:** [docs/CONTRACTS.md](docs/CONTRACTS.md) lists frozen schemas (runner output, queue, invariant registry, enforcement, receipt, evidence bundle, FHIR, results v0.2 semantics; v0.3 extensible only).
- **Quickstart (paper artifact):** `bash scripts/quickstart_paper_v0_1.sh` (or `scripts/quickstart_paper_v0.1.ps1` on Windows): install → validate-policy → quick-eval → package-release paper_v0.1 → verify-bundle.
- **UI fixtures:** [ui_fixtures/](ui_fixtures/) contains minimal results.v0.2, episode log, evidence bundle, and FHIR bundle for offline UI work. **UI data contract:** [docs/ui_data_contract.md](docs/ui_data_contract.md) specifies ui-export bundle format; the UI depends on `labtrust ui-export` output, not raw internal logs.

## License

Apache-2.0.
