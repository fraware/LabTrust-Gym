# LabTrust-Gym

**A multi-agent environment (PettingZoo/Gym) for a self-driving hospital lab, with a reference trust skeleton.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/downloads/)

RBAC, signed actions, append-only audit log, invariants, and anomaly throttles—all driven by versioned policy and golden scenarios.

---

## North star

| Pillar | Goal |
|--------|------|
| **Environment** | Pip-installable, standard multi-agent API (PettingZoo AEC or parallel). |
| **Trust skeleton** | Roles/permissions, signed actions, hash-chained audit log, invariants, reason codes. |
| **Benchmarks** | Tasks and baselines (scripted, MARL, LLM) with clear safety/throughput trade-offs. |

## Principles

- **Golden scenarios drive development** — The simulator is correct when the golden suite passes.
- **Policy is data** — Invariants, tokens, reason codes, catalogue, zones live in versioned files under `policy/`.
- **Determinism** — Golden runs are deterministic (seeded RNG, no ambient randomness).
- **No silent failure** — Missing hooks or invalid data fail loudly with reason codes.
- For system and threat model context, see [Systems and threat model](docs/architecture/systems_and_threat_model.md).

---

## Installation (pip)

**From PyPI** (env + plots for benchmarks and quick-eval):

```bash
pip install labtrust-gym[env,plots]
labtrust --version
labtrust quick-eval
```

Quick-eval runs one episode each of `throughput_sla`, `adversarial_disruption`, and `multi_site_stat` with scripted baselines, prints a markdown summary, and stores logs under `./labtrust_runs/`.

**From source** (development):

```bash
git clone https://github.com/fraware/LabTrust-Gym.git
cd LabTrust-Gym
pip install -e ".[dev]"
labtrust validate-policy
pytest -q
```

Run from the **repo root** so that `policy/` is found; otherwise you may see **PolicyPathError** (policy directory not found). You can override the policy path with **LABTRUST_POLICY_DIR** (must point to an existing policy directory). See [Installation](docs/getting-started/installation.md) and [Troubleshooting](docs/getting-started/troubleshooting.md#policy-directory-not-found-policypatherror).

**Full stack** (benchmarks, studies, plots; PettingZoo + matplotlib):

```bash
pip install -e ".[dev,env,plots]"
labtrust run-benchmark --task throughput_sla --episodes 5 --out results.json
labtrust reproduce --profile minimal
```

**New to the repo?** If you forked the repo and want to customize for your hospital lab and run all commands end-to-end, see [Forker guide](docs/getting-started/forkers.md) and [Quick demos](docs/getting-started/quick_demos.md).

**Extending without forking**

- **Option A:** Fork and customize via partner overlay and policy only. See [Forker guide](docs/getting-started/forkers.md).
- **Option B:** Install `labtrust-gym` and ship your own pip package that registers domains, tasks, coordination methods, invariant handlers, or providers via `register_*` or entry_points; use `--profile` to set partner and provider IDs and `extension_packages`. See [Extension development](docs/agents/extension_development.md#integration-pattern-option-b).

| Extra | Purpose |
|-------|---------|
| `[env]` | PettingZoo/Gymnasium |
| `[plots]` | Matplotlib |
| `[marl]` | Stable-Baselines3 (PPO train/eval, PPOAgent) |
| `[marl_hpo]` | Optuna (hyperparameter search for PPO; use with marl) |
| `[docs]` | MkDocs + mkdocstrings |

---

## Pipelines

Benchmarks run in one of three pipeline modes: **deterministic** | **llm_offline** | **llm_live** (only these values; see [Live LLM](docs/agents/llm_live.md) for canonical definitions). **Defaults are offline** (no network, no API cost).

| Mode | Network | Agents | Use case |
|------|---------|--------|----------|
| **deterministic** | No | Scripted only | CI, regression, reproduce, paper artifact (default) |
| **llm_offline** | No | LLM interface, deterministic backend only | Offline LLM evaluation, no API calls |
| **llm_live** | Yes (opt-in) | Live OpenAI/Ollama | Interactive or cost-accepting runs; requires `--allow-network` |

Set mode with `--pipeline-mode`; for live LLM also pass `--allow-network` or `LABTRUST_ALLOW_NETWORK=1`. See [Live LLM](docs/agents/llm_live.md) and [Installation](docs/getting-started/installation.md#configuration-no-env-file-required).

> **Why you saw no OpenAI calls**  
> Runs are **offline by default**. `quick-eval`, `run-benchmark`, `reproduce`, and `package-release` use `pipeline_mode=deterministic` unless you pass `--pipeline-mode llm_live` and `--allow-network`. No `.env` or `OPENAI_API_KEY` is read unless the pipeline is **llm_live** and network is allowed.  
> To run with a live LLM: `--pipeline-mode llm_live --allow-network --llm-backend openai_live` (or `ollama_live`). The CLI prints: **WILL MAKE NETWORK CALLS / MAY INCUR COST**.  
> Every run records `pipeline_mode`, `llm_backend_id`, `llm_model_id`, and `allow_network` in **results.json** (and UI export **index.json**) for audit. All benchmark result files also record **non_deterministic** so you can tell deterministic vs LLM runs when inspecting outputs.

---

## Quick eval

After `pip install labtrust-gym[env,plots]`:

```bash
labtrust quick-eval
```

Output: markdown summary (throughput, violations, blocked counts) and logs under `./labtrust_runs/quick_eval_<timestamp>/`. Use `--seed` and `--out-dir` to customize.

**Quick demos:** The canonical demo commands are `labtrust forker-quickstart`, `labtrust quick-eval`, and `labtrust run-official-pack` (use `--include-coordination-pack` when you want coordination and security evidence in one run). See [Quick demos](docs/getting-started/quick_demos.md) for a table of "if you want to see X, run Y."

### Example agents and notebooks

See [Example experiments](docs/getting-started/example_experiments.md) for trust-vs-performance experiments. Example agents (scripted, random, LLM mock, external) and configs are in `examples/`. An optional Jupyter notebook `examples/quick_eval.ipynb` runs quick-eval from the repo root (requires `.[env,plots]`). Run a benchmark with an external agent:

```bash
labtrust eval-agent --agent 'examples.external_agent_demo:MyAgent' --task throughput_sla --episodes 2 --out out.json
```

---

## CLI

Keep the repo root minimal; put CLI outputs in `labtrust_runs/` or `--out` (see [Repository structure](docs/reference/repository_structure.md)). For exit codes, minimal smoke args, and expected output paths, see [CLI output contract](docs/contracts/cli_contract.md). All listed commands are smoke-tested with minimal args in `tests/test_cli_smoke_matrix.py` (CI runs this after main pytest).

### Policy and validation

| Command | Description |
|---------|-------------|
| **validate-policy** | Validate all policy YAML/JSON against schemas. |
| **forker-quickstart** | One-command forker: validate-policy, coordination pack, lab report, risk register export. See [Forker guide](docs/getting-started/forkers.md). |

### Benchmarking and evaluation

| Command | Description |
|---------|-------------|
| **quick-eval** | One episode each of throughput_sla, adversarial_disruption, multi_site_stat; summary + logs under `./labtrust_runs/`. |
| **run-benchmark** | Run tasks (throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse, coord_scale, coord_risk); write results.json. Options: `--task`, `--episodes`, `--out`, `--coord-method`, `--injection`, `--scale`, `--timing`, `--llm-backend`, `--llm-agents`. See [Live LLM](docs/agents/llm_live.md), [LLM Coordination Protocol](docs/benchmarks/llm_coordination_protocol.md). |
| **eval-agent** | Run benchmark with external agent (e.g. `--agent "examples.external_agent_demo:SafeNoOpAgent"` or trained PPO: set `LABTRUST_PPO_MODEL=<path>/model.zip`, `--agent labtrust_gym.baselines.marl.ppo_agent:PPOAgent`). |
| **bench-smoke** | One episode per task (throughput_sla, stat_insertion, qc_cascade). |
| **determinism-report** | Run benchmark twice in fresh temp dirs; assert v0.2 metrics and episode log hash identical; write determinism_report.md/json. |
| **train-ppo**, **eval-ppo** | PPO training/eval (requires `.[marl]`). Writes `train_config.json`; eval-ppo auto-loads it. Optional HPO: `.[marl_hpo]`. See [MARL baselines](docs/agents/marl_baselines.md). |

### Export and verification

| Command | Description |
|---------|-------------|
| **export-receipts** | Export Receipt.v0.1 and EvidenceBundle.v0.1 from episode log. |
| **export-fhir** | Export valid HL7 FHIR R4 Bundle from receipts dir (data-absent-reason for missing specimen/value; no placeholder IDs). See [FHIR R4 export](docs/export/fhir_export.md). |
| **verify-bundle** | Verify a **single** EvidenceBundle.v0.1 (manifest, schema, hashchain, invariant trace). Use `--strict-fingerprints` to require coordination, memory, rbac, and tool_registry fingerprints. |
| **verify-release** | Verify release end-to-end: all EvidenceBundles, optional risk register bundle (schema + crosswalk), and RELEASE_MANIFEST.v0.1.json hashes. Use `--strict-fingerprints` for releases (default in CI). See [Release checklist](docs/operations/release_checklist.md). |
| **build-release-manifest** | Write RELEASE_MANIFEST.v0.1.json with hashes of MANIFEST, evidence bundles, and risk register bundle. Run after export-risk-register into the release dir; then verify-release validates everything offline. |
| **ui-export** | Export UI-ready zip (index, events, receipts_index, reason_codes). See [UI data contract](docs/contracts/ui_data_contract.md). |

### Security and safety

| Command | Description |
|---------|-------------|
| **run-security-suite** | Security attack suite (smoke/full); SECURITY/attack_results.json and securitization packet. See [Security attack suite](docs/risk-and-security/security_attack_suite.md). Prompt-injection defenses: pre-LLM block, output consistency; policy `policy/security/prompt_injection_defense.v0.1.yaml`. See [Prompt-injection defense](docs/risk-and-security/prompt_injection_defense.md), [Security monitoring](docs/risk-and-security/security_monitoring.md). |
| **safety-case** | Generate safety case to SAFETY_CASE/. See [Risk register](docs/risk-and-security/risk_register.md) (safety case evidence). |
| **run-official-pack** | Official Benchmark Pack v0.1 (tasks, scales, baselines, coordination, security, safety case, transparency log). See [Official benchmark pack](docs/benchmarks/official_benchmark_pack.md). |

### Risk register

| Command | Description |
|---------|-------------|
| **export-risk-register** | Export RiskRegisterBundle.v0.1 to a directory. Bundle represents evidence gaps (status=missing) as first-class; no placeholder wording. CI contract gate: schema, snapshot, crosswalk, coverage. See [Risk register](docs/risk-and-security/risk_register.md). |
| **build-risk-register-bundle** | Build same bundle to an explicit file path. |
| **validate-coverage** | Validate bundle coverage (required_bench cells evidenced or waived). Use `--strict` to fail if any required risk has missing evidence. |

### Coordination and studies

| Command | Description |
|---------|-------------|
| **run-coordination-study** | Scale × method × injection; cells, summary_coord.csv, pareto.md, SOTA leaderboard. See [Coordination studies](docs/coordination/coordination_studies.md), [Risk register](docs/risk-and-security/risk_register.md). |
| **run-coordination-security-pack** | Internal coordination security regression pack (fixed matrix, deterministic). See [Security attack suite](docs/risk-and-security/security_attack_suite.md#coordination-security-pack-internal-regression). |
| **summarize-coordination** | Aggregate coordination results; SOTA leaderboard and method-class comparison. |
| **recommend-coordination-method** | Produce COORDINATION_DECISION.v0.1.json from run dir. |
| **build-coordination-matrix** | Build CoordinationMatrix v0.1 from llm_live coordination run. |
| **run-study** | Run study from spec (`--spec`, `--out`). |
| **make-plots** | Generate figures and data tables from a study run. |

### Release and reproducibility

| Command | Description |
|---------|-------------|
| **reproduce** | Minimal/full results + figures (`--profile minimal | full`). See [Reproduce](docs/benchmarks/reproduce.md). |
| **package-release** | Release artifact: reproduce + receipts + FHIR + plots + MANIFEST + BENCHMARK_CARD + summary. Use `--profile paper_v0.1` for paper-ready artifact. See [Paper provenance](docs/benchmarks/paper/README.md) and [Release checklist](docs/operations/release_checklist.md). |
| **generate-official-baselines** | Run core tasks with official baselines; write results/, summary, metadata. Registry: `benchmarks/baseline_registry.v0.1.yaml`. |
| **summarize-results** | Stream results (bounded memory); write summary_v0.2.csv, summary_v0.3.csv, summary.md. Handles large result dirs. See [Metrics contract](docs/contracts/metrics_contract.md). |
| **serve** | Online HTTP server (auth, rate limits; summary/episode-log endpoints). See [Security controls (online)](docs/risk-and-security/security_online.md), [Output controls](docs/risk-and-security/output_controls.md). |

---

## Repository structure

| Path | Description |
|------|-------------|
| **policy/** | Versioned YAML/JSON: schemas, emits, invariants, tokens, reason_codes, zones, catalogue, coordination, golden, official, llm, partners, **risks** (risk_registry, waivers, required_bench_plan.v0.1). Validated by `labtrust validate-policy`. |
| **src/labtrust_gym/** | Package: config, engine/, envs/ (PettingZoo), baselines/, benchmarks/, policy/, security/, studies/, export/, online/, runner/, cli/. |
| **tests/** | Pytest: golden suite, policy, benchmarks, coordination, risk_injections, studies, export, online, CLI smoke matrix (`test_cli_smoke_matrix.py`). |
| **benchmarks/** | Baseline registry, official baselines (v0.1, v0.2). |
| **examples/** | Example agents (external_agent_demo, scripted_ops_agent, llm_agent_mock_demo, etc.). |
| **docs/** | MkDocs: architecture, benchmarks, coordination ([methods](docs/coordination/coordination_methods.md)), [benchmarking plan](docs/benchmarks/benchmarking_plan.md), [frozen contracts](docs/contracts/frozen_contracts.md), [getting started](docs/getting-started/index.md), security, LLM, MARL. [Forker guide](docs/getting-started/forkers.md) for fork-to-run and customization. |
| **scripts/** | Quickstart, paper-release, benchmarking (run_benchmarking_layer1_sanity, run_external_reviewer_checks), **run_required_bench_matrix** (plan-driven: required_bench_plan.v0.1.yaml), **extract_paper_claims_snapshot** (paper regression snapshot), build_release_fixture, build_viewer_data_from_release. |
| **tests/fixtures/ui_fixtures/** | Minimal results, episode log, evidence bundle for offline UI. |

---

## Golden runner

The golden runner (`labtrust_gym.runner`) runs scenario scripts from `policy/golden/golden_scenarios.v0.1.yaml` against an environment adapter. The adapter must implement `LabTrustEnvAdapter` (reset, step, query). Step results must conform to the runner output contract (status, emits, violations, hashchain, etc.). Unknown emits fail the suite. Full suite: `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py`.

---

## Reproducibility and citation

- **Reproduce:** `labtrust reproduce --profile minimal` — [Reproduce](docs/benchmarks/reproduce.md).
- **Release artifact:** `labtrust package-release --profile minimal --out /tmp/labtrust_release` produces MANIFEST, BENCHMARK_CARD, metadata, results (v0.2), summary, plots, receipts, FHIR. For paper-ready: `--profile paper_v0.1` — [Paper provenance](docs/benchmarks/paper/README.md), [Security attack suite](docs/risk-and-security/security_attack_suite.md), [Coordination benchmark card](docs/coordination/coordination_benchmark_card.md).
- **For research and audit:** Use the paper-ready artifact and verify-release so high-impact is linked to a verifiable, citable artifact: [Quick demos](docs/getting-started/quick_demos.md) and [Paper provenance](docs/benchmarks/paper/README.md).
- **Standardized evaluation:** The [Benchmark card](docs/benchmarks/benchmark_card.md) and official baselines (v0.2) are the public contract for what we measure and how we compare. See [Use cases and impact](docs/reference/use_cases_and_impact.md).
- **Official baselines:** v0.2 is canonical in `benchmarks/baselines_official/v0.2/`. Regenerate: `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force`. Compare: `labtrust summarize-results --in benchmarks/baselines_official/v0.2/results/ your_results.json --out /tmp/compare` — [Benchmark card](docs/benchmarks/benchmark_card.md).
- **Cite:** [CITATION.cff](CITATION.cff) or *LabTrust-Gym: a multi-agent environment for a self-driving hospital lab with a trust skeleton*. https://github.com/fraware/LabTrust-Gym.

---

## Improvements before going online

Before adding online APIs and non-deterministic runs, see [CI](docs/operations/ci.md) and [Release checklist](docs/operations/release_checklist.md). CI includes: **risk-register-gate** (schema, snapshot, crosswalk), **risk-coverage-every-pr** (validate-coverage --strict), **coverage** (fail_under ratchet; see [CI — coverage](docs/operations/ci.md#coverage-report-and-ratchet)), **golden** job (determinism-report then full golden suite; determinism budget enforced), **verify-release** with --strict-fingerprints in the E2E artifacts chain. Golden suite and determinism-report run on every PR; pytest timeout for long tests; summarize uses streaming for bounded memory.

---

## Current state

The test suite runs with `pytest -v` (extensive test suite; PettingZoo smoke, MARL smoke, golden suite, and optional-backend tests may be skipped depending on env). Implemented: policy validation, hashchain, tokens, zones, specimens, QC, critical results (v0.2), transport, export, package-release, risk register, security (attack suite, safety case, **prompt-injection defense**), coordination red team, Official Benchmark Pack, online serve, PettingZoo wrappers (with `render_mode`), scripted/adversary/LLM/MARL baselines, PPO (train_config, obs_history_len, reward curriculum, Optuna HPO, PPOAgent with train_config.json), **SOTA coordination methods** (consensus_paxos_lite, swarm_stigmergy_priority), **engine state/event** (state.py, event.py with InitialStateDict/StepEventDict), **risk-coverage-strict** CI job (schedule/manual), **paper provenance** ([Paper provenance](docs/benchmarks/paper/README.md)), **LLM coordination standards-of-excellence** checklist ([Live LLM](docs/agents/llm_live.md)), and docs site.

---

## Release and contract freeze

- **Release checklist:** Run the E2E artifacts chain before tagging. [Release checklist](docs/operations/release_checklist.md), [CONTRIBUTING](CONTRIBUTING.md). From repo root: **`make verify`** runs the full verification battery; **`make paper OUT=<dir>`** builds a paper-ready artifact; **`labtrust audit-selfcheck --out <dir>`** runs Phase A audit checks plus doctor-style checks (Python path, venv, extras, filesystem, policy; CI: audit-selfcheck.yml; wheel-smoke runs it after install). **Paper claims regression:** snapshot at tests/fixtures/paper_claims_snapshot/v0.1; CI job on schedule/workflow_dispatch — [Paper claims](docs/benchmarks/PAPER_CLAIMS.md).
- **Version:** `labtrust --version` prints version + git SHA. Tag from a clean main commit after the checklist.
- **Contract freeze:** [Frozen contracts](docs/contracts/frozen_contracts.md) — runner output, queue, invariant registry, enforcement, receipt, evidence bundle, FHIR, results v0.2 semantics; v0.3 extensible only.
- **Quickstart (paper):** `bash scripts/quickstart_paper_v0_1.sh` or `scripts/quickstart_paper_v0.1.ps1` on Windows: install → validate-policy → quick-eval → package-release paper_v0.1 → verify-release. For full release artifact (evidence + risk register + hashes): run export-risk-register into the release dir, then build-release-manifest, then verify-release --strict-fingerprints. See [Release checklist](docs/operations/release_checklist.md).
- **UI:** [tests/fixtures/ui_fixtures/](tests/fixtures/ui_fixtures/) — minimal results, episode log, evidence bundle. [UI data contract](docs/contracts/ui_data_contract.md) — ui-export bundle format.

---

## License

Apache-2.0.
