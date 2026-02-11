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

**Full stack** (benchmarks, studies, plots; PettingZoo + matplotlib):

```bash
pip install -e ".[dev,env,plots]"
labtrust run-benchmark --task throughput_sla --episodes 5 --out results.json
labtrust reproduce --profile minimal
```

| Extra | Purpose |
|-------|---------|
| `[env]` | PettingZoo/Gymnasium |
| `[plots]` | Matplotlib |
| `[marl]` | Stable-Baselines3 |
| `[docs]` | MkDocs + mkdocstrings |

---

## Pipelines

Benchmarks run in one of three pipeline modes. **Defaults are offline** (no network, no API cost).

| Mode | Network | Agents | Use case |
|------|---------|--------|----------|
| **deterministic** | No | Scripted only | CI, regression, reproduce, paper artifact (default) |
| **llm_offline** | No | LLM interface, deterministic backend only | Offline LLM evaluation, no API calls |
| **llm_live** | Yes (opt-in) | Live OpenAI/Ollama | Interactive or cost-accepting runs; requires `--allow-network` |

Set mode with `--pipeline-mode`; for live LLM also pass `--allow-network` or `LABTRUST_ALLOW_NETWORK=1`. See [docs/llm_live.md](docs/llm_live.md) and [docs/installation.md](docs/installation.md#configuration-no-env-file-required).

> **Why you saw no OpenAI calls**  
> Runs are **offline by default**. `quick-eval`, `run-benchmark`, `reproduce`, and `package-release` use `pipeline_mode=deterministic` unless you pass `--pipeline-mode llm_live` and `--allow-network`. No `.env` or `OPENAI_API_KEY` is read unless the pipeline is **llm_live** and network is allowed.  
> To run with a live LLM: `--pipeline-mode llm_live --allow-network --llm-backend openai_live` (or `ollama_live`). The CLI prints: **WILL MAKE NETWORK CALLS / MAY INCUR COST**.  
> Every run records `pipeline_mode`, `llm_backend_id`, `llm_model_id`, and `allow_network` in **results.json** (and UI export **index.json**) for audit.

---

## Quick eval

After `pip install labtrust-gym[env,plots]`:

```bash
labtrust quick-eval
```

Output: markdown summary (throughput, violations, blocked counts) and logs under `./labtrust_runs/quick_eval_<timestamp>/`. Use `--seed` and `--out-dir` to customize.

---

## CLI

Keep the repo root minimal; put CLI outputs in `labtrust_runs/` or `--out` (see [Repository structure](docs/repository_structure.md)). For exit codes, minimal smoke args, and expected output paths, see [CLI output contract](docs/cli_contract.md). All listed commands are smoke-tested with minimal args in `tests/test_cli_smoke_matrix.py` (CI runs this after main pytest).

### Policy and validation

| Command | Description |
|---------|-------------|
| **validate-policy** | Validate all policy YAML/JSON against schemas. |
| **forker-quickstart** | One-command forker: validate-policy, coordination pack, lab report, risk register export. See [Forker guide](docs/FORKER_GUIDE.md). |

### Benchmarking and evaluation

| Command | Description |
|---------|-------------|
| **quick-eval** | One episode each of throughput_sla, adversarial_disruption, multi_site_stat; summary + logs under `./labtrust_runs/`. |
| **run-benchmark** | Run tasks (throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse, coord_scale, coord_risk); write results.json. Options: `--task`, `--episodes`, `--out`, `--coord-method`, `--injection`, `--scale`, `--timing`, `--llm-backend`, `--llm-agents`. See [docs/llm_live.md](docs/llm_live.md), [docs/llm_coordination_protocol.md](docs/llm_coordination_protocol.md). |
| **eval-agent** | Run benchmark with external agent (e.g. `--agent "examples.external_agent_demo:SafeNoOpAgent"`). |
| **bench-smoke** | One episode per task (throughput_sla, stat_insertion, qc_cascade). |
| **determinism-report** | Run benchmark twice in fresh temp dirs; assert v0.2 metrics and episode log hash identical; write determinism_report.md/json. |
| **train-ppo**, **eval-ppo** | PPO training/eval (requires `.[marl]`). |

### Export and verification

| Command | Description |
|---------|-------------|
| **export-receipts** | Export Receipt.v0.1 and EvidenceBundle.v0.1 from episode log. |
| **export-fhir** | Export FHIR R4 Bundle from receipts dir. |
| **verify-bundle** | Verify a **single** EvidenceBundle.v0.1 (manifest, schema, hashchain, invariant trace). |
| **verify-release** | Verify **all** EvidenceBundles under a release dir (output of package-release). |
| **ui-export** | Export UI-ready zip (index, events, receipts_index, reason_codes). See [docs/ui_data_contract.md](docs/ui_data_contract.md). |

### Security and safety

| Command | Description |
|---------|-------------|
| **run-security-suite** | Security attack suite (smoke/full); SECURITY/attack_results.json and securitization packet. See [docs/security_attack_suite.md](docs/security_attack_suite.md). |
| **safety-case** | Generate safety case to SAFETY_CASE/. See [docs/implementation_verification.md](docs/implementation_verification.md). |
| **run-official-pack** | Official Benchmark Pack v0.1 (tasks, scales, baselines, coordination, security, safety case, transparency log). See [docs/official_benchmark_pack.md](docs/official_benchmark_pack.md). |

### Risk register

| Command | Description |
|---------|-------------|
| **export-risk-register** | Export RiskRegisterBundle.v0.1 to a directory. CI contract gate: schema, snapshot, crosswalk, coverage. See [docs/risk_register.md](docs/risk_register.md). |
| **build-risk-register-bundle** | Build same bundle to an explicit file path. |

### Coordination and studies

| Command | Description |
|---------|-------------|
| **run-coordination-study** | Scale × method × injection; cells, summary_coord.csv, pareto.md, SOTA leaderboard. See [Coordination studies](docs/coordination_studies.md), [Risk register](docs/risk_register.md). |
| **run-coordination-security-pack** | Internal coordination security regression pack (fixed matrix, deterministic). See [Security attack suite](docs/security_attack_suite.md#coordination-security-pack-internal-regression). |
| **summarize-coordination** | Aggregate coordination results; SOTA leaderboard and method-class comparison. |
| **recommend-coordination-method** | Produce COORDINATION_DECISION.v0.1.json from run dir. |
| **build-coordination-matrix** | Build CoordinationMatrix v0.1 from llm_live coordination run. |
| **run-study** | Run study from spec (`--spec`, `--out`). |
| **make-plots** | Generate figures and data tables from a study run. |

### Release and reproducibility

| Command | Description |
|---------|-------------|
| **reproduce** | Minimal/full results + figures (`--profile minimal | full`). See [docs/reproduce.md](docs/reproduce.md). |
| **package-release** | Release artifact: reproduce + receipts + FHIR + plots + MANIFEST + BENCHMARK_CARD + summary. Use `--profile paper_v0.1` for paper-ready artifact. See [docs/paper_ready.md](docs/paper_ready.md). |
| **generate-official-baselines** | Run core tasks with official baselines; write results/, summary, metadata. Registry: `benchmarks/baseline_registry.v0.1.yaml`. |
| **summarize-results** | Aggregate results; write summary_v0.2.csv, summary_v0.3.csv, summary.md. See [docs/metrics_contract.md](docs/metrics_contract.md). |
| **serve** | Online HTTP server (auth, rate limits; summary/episode-log endpoints). See [docs/security_online.md](docs/security_online.md), [docs/output_controls.md](docs/output_controls.md). |

---

## Repository structure

| Path | Description |
|------|-------------|
| **policy/** | Versioned YAML/JSON: schemas, emits, invariants, tokens, reason_codes, zones, catalogue, coordination, golden, official, llm, partners. Validated by `labtrust validate-policy`. |
| **src/labtrust_gym/** | Package: config, engine/, envs/ (PettingZoo), baselines/, benchmarks/, policy/, security/, studies/, export/, online/, runner/, cli/. |
| **tests/** | Pytest: golden suite, policy, benchmarks, coordination, risk_injections, studies, export, online, CLI smoke matrix (`test_cli_smoke_matrix.py`). |
| **benchmarks/** | Baseline registry, official baselines (v0.1, v0.2). |
| **examples/** | Example agents (external_agent_demo, scripted_ops_agent, llm_agent_mock_demo, etc.). |
| **docs/** | MkDocs: architecture, benchmarks, coordination ([methods](docs/coordination_methods.md)), [benchmarking plan](docs/benchmarking_plan.md), [frozen contracts](docs/frozen_contracts.md), installation, [STATUS](docs/STATUS.md), security, LLM, MARL. |
| **scripts/** | Quickstart, paper-release, benchmarking (run_benchmarking_layer1_sanity, run_external_reviewer_checks). |
| **tests/fixtures/ui_fixtures/** | Minimal results, episode log, evidence bundle for offline UI. |

---

## Golden runner

The golden runner (`labtrust_gym.runner`) runs scenario scripts from `policy/golden/golden_scenarios.v0.1.yaml` against an environment adapter. The adapter must implement `LabTrustEnvAdapter` (reset, step, query). Step results must conform to the runner output contract (status, emits, violations, hashchain, etc.). Unknown emits fail the suite. Full suite: `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py`.

---

## Reproducibility and citation

- **Reproduce:** `labtrust reproduce --profile minimal` — [docs/reproduce.md](docs/reproduce.md).
- **Release artifact:** `labtrust package-release --profile minimal --out /tmp/labtrust_release` produces MANIFEST, BENCHMARK_CARD, metadata, results (v0.2), summary, plots, receipts, FHIR. For paper-ready: `--profile paper_v0.1` — [docs/paper_ready.md](docs/paper_ready.md), [docs/security_attack_suite.md](docs/security_attack_suite.md), [docs/coordination_benchmark_card.md](docs/coordination_benchmark_card.md).
- **Official baselines:** v0.2 is canonical in `benchmarks/baselines_official/v0.2/`. Regenerate: `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force`. Compare: `labtrust summarize-results --in benchmarks/baselines_official/v0.2/results/ your_results.json --out /tmp/compare` — [Benchmark card](docs/benchmark_card.md).
- **Cite:** [CITATION.cff](CITATION.cff) or *LabTrust-Gym: a multi-agent environment for a self-driving hospital lab with a trust skeleton*. https://github.com/fraware/LabTrust-Gym.

---

## Improvements before going online

Before adding online APIs and non-deterministic runs, see **[docs/STATUS.md](docs/STATUS.md#improvements-before-online-checklist)** for the checklist: stability (tests/fixtures/ui_fixtures, long tests), code optimization (policy loading, large JSONL, summarize/export), testing (pytest timeout, coverage, CI), documentation, and pre-online readiness. Some items are done; others remain (e.g. golden suite in CI, determinism-report coverage, pytest timeout for long tests).

---

## Current state

See **docs/STATUS.md** for the full report: policy validation, hashchain, tokens, zones, specimens, QC, critical results (v0.2), transport, export, package-release, risk register, security (attack suite, safety case), coordination red team, Official Benchmark Pack, online serve, PettingZoo wrappers, scripted/adversary/LLM/MARL baselines, TaskA–TaskH, quick-eval, PyPI packaging, studies, and docs site.

---

## Release and contract freeze

- **Release checklist:** Run the E2E artifacts chain before tagging. [Release checklist](docs/release_checklist.md), [CONTRIBUTING](CONTRIBUTING.md).
- **Version:** `labtrust --version` prints version + git SHA. Tag from a clean main commit after the checklist.
- **Contract freeze:** [docs/frozen_contracts.md](docs/frozen_contracts.md) — runner output, queue, invariant registry, enforcement, receipt, evidence bundle, FHIR, results v0.2 semantics; v0.3 extensible only.
- **Quickstart (paper):** `bash scripts/quickstart_paper_v0_1.sh` or `scripts/quickstart_paper_v0.1.ps1` on Windows: install → validate-policy → quick-eval → package-release paper_v0.1 → verify-release.
- **UI:** [tests/fixtures/ui_fixtures/](tests/fixtures/ui_fixtures/) — minimal results, episode log, evidence bundle. [docs/ui_data_contract.md](docs/ui_data_contract.md) — ui-export bundle format.

---

## License

Apache-2.0.
