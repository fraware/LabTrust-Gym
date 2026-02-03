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

**LLMs:** Benchmarks and tests use **deterministic, offline** LLM backends by default (no API keys or `.env`). Optional **live LLM** mode: `--llm-backend openai_live` (requires `OPENAI_API_KEY`; non-deterministic, incurs cost). See [docs/installation.md](docs/installation.md#configuration-no-env-file-required), [docs/llm_baselines.md](docs/llm_baselines.md), and [docs/llm_live.md](docs/llm_live.md).

## Quick eval

After `pip install labtrust-gym[env,plots]`, run a minimal sanity check (1 episode each of TaskA, TaskD, TaskE):

```bash
labtrust quick-eval
```

Output: a markdown summary (throughput, violations, blocked counts) and logs under `./labtrust_runs/quick_eval_<timestamp>/`. Use `--seed` and `--out-dir` to customize.

## CLI

- **validate-policy** — Validate all policy YAML/JSON against schemas.
- **quick-eval** — 1 episode each of TaskA, TaskD, TaskE; markdown summary and logs under `./labtrust_runs/` (`--seed`, `--out-dir`).
- **run-benchmark** — Run TaskA, TaskB, TaskC, TaskD, TaskE, or TaskF; write results.json (`--task`, `--episodes`, `--out`). Optional `--llm-backend {deterministic,openai_live}` to use LLM agent (default: scripted agents); see [docs/llm_live.md](docs/llm_live.md).
- **eval-agent** — Run benchmark with an external agent (module:Class or module:function); write results.json (v0.2). Example: `--agent "examples.external_agent_demo:SafeNoOpAgent"` (`--task`, `--episodes`, `--out`, `--seed`, `--partner`, `--timing`).
- **bench-smoke** — 1 episode per task (TaskA, TaskB, TaskC).
- **export-receipts** — Export Receipt.v0.1 and EvidenceBundle.v0.1 from episode log (`--run`, `--out`).
- **export-fhir** — Export FHIR R4 Bundle from receipts dir (`--receipts`, `--out`).
- **verify-bundle** — Verify EvidenceBundle.v0.1: manifest integrity, schema, hashchain, invariant trace (`--bundle`, `--allow-extra-files`).
- **ui-export** — Export UI-ready zip (index, events, receipts_index, reason_codes) from a run dir (`--run`, `--out`). UI consumes this as primary input; see [docs/ui_data_contract.md](docs/ui_data_contract.md).
- **run-study** — Run study from spec (`--spec`, `--out`); ablations → conditions → results.
- **make-plots** — Generate figures and data tables from a study run (`--run`).
- **reproduce** — Reproduce minimal results + figures: TaskA & TaskC sweep + plots (`--profile minimal | full`, optional `--out`, `--seed-base`).
- **package-release** — Release candidate artifact: reproduce + receipts + FHIR + plots + MANIFEST + BENCHMARK_CARD + summary table (`--profile minimal | full | paper_v0.1`, `--out`, optional `--seed-base`, `--keep-repro`). Use **paper_v0.1** for a benchmark-first, paper-ready artifact (baselines + TaskF study + summarize + receipts + FIGURES/TABLES); see [docs/paper_ready.md](docs/paper_ready.md).
- **generate-official-baselines** — Run Tasks A–F with official baselines; write results/, summary.csv, summary.md, metadata.json (`--out`, `--episodes`, `--seed`, `--timing`, `--partner`, `--force`). Registry: `benchmarks/baseline_registry.v0.1.yaml`.
- **summarize-results** — Load results.json from dir(s)/file(s), aggregate by task+baseline+partner_id; write **summary_v0.2.csv** (CI-stable), **summary_v0.3.csv** (paper-grade: quantiles, 95% CI), **summary.csv** (copy of v0.2), and summary.md (`--in`, `--out`, `--basename`). See [docs/metrics_contract.md](docs/metrics_contract.md). Compare to official baselines in `benchmarks/baselines_official/v0.1/` (or regenerate v0.2 with generate-official-baselines).
- **determinism-report** — Run benchmark twice with identical args in fresh temp dirs; write **determinism_report.md** and **determinism_report.json** (sha256 of episode logs, results.json, receipts bundle root hash); assert v0.2 metrics and episode log hash identical (`--task`, `--episodes`, `--seed`, `--out`, optional `--partner`, `--timing explicit|simulated`). With `--timing simulated`, device service-time sampling is seeded only from `--seed`.
- **train-ppo**, **eval-ppo** — PPO training/eval (requires `.[marl]`).

## Layout

- **policy/** — Versioned YAML/JSON: `schemas/`, `emits/`, `invariants/` (registry v1.0), `tokens/`, `reason_codes/`, `zones/`, `sites/` (sites_policy), `catalogue/`, `stability/`, `equipment/`, `critical/` (thresholds, escalation_ladder v0.2), `enforcement/`, `studies/`, `llm/`, `golden/`, `partners/`. Validated by `labtrust validate-policy`.
- **src/labtrust_gym/** — `config.py` (get_repo_root for policy path), `engine/` (core_env, audit_log, zones, specimens, qc, critical, queueing, devices, clock, rng, transport, catalogue_runtime, tokens_runtime, invariants_runtime, enforcement), `policy/` (loader, validate, invariants_registry), `export/` (receipts, fhir_r4), `runner/`, `envs/` (PettingZoo Parallel and AEC), `baselines/` (scripted_ops, scripted_runner, adversary, **llm** (allowed_actions_payload, ProviderBackend, LLM_DECISION audit), marl), `benchmarks/`, `studies/` (study_runner, plots, reproduce, package_release), `logging/`, `cli/`, `version.py`.
- **tests/** — Golden suite, policy validation, hashchain, tokens, zones, specimens, qc, critical, queueing, benchmarks, invariant registry, enforcement, **test_signatures_key_lifecycle** (key lifecycle: valid/revoked/expired/not-yet-valid), **test_llm_constrained_decoder** (LLM constrained decode, rationale, deterministic baseline, LLM_DECISION audit), **test_openai_live** (live backend, LLM_DECISION shape), transport, export_receipts, fhir_export, package_release, study runner, plots, reproduce smoke, adversary, marl smoke, llm agent mock.
- **examples/** — `minimal_random_policy_agent.py`, `scripted_ops_agent.py`, `scripted_runner_agent.py`, `llm_agent_mock_demo.py`.
- **docs/** — Architecture, policy pack, invariants & enforcement, benchmarks, studies, reproduce, PettingZoo API, CI, threat model, MARL/LLM baselines, **llm_live** (live LLM benchmark mode); **docs/STATUS.md** — current state. MkDocs site (build with `.[docs]`).

## Golden runner

The golden runner (`labtrust_gym.runner`) runs scenario scripts from `policy/golden/golden_scenarios.v0.1.yaml` against an environment adapter. The adapter must implement `LabTrustEnvAdapter` (reset, step, query). Step results must conform to the runner output contract (status, emits, violations, hashchain, etc.). Unknown emits fail the suite. With the real engine the full golden suite passes: `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py`.

## Reproducibility and citation

- **Reproduce**: `labtrust reproduce --profile minimal` (see [docs/reproduce.md](docs/reproduce.md)).
- **Release artifact**: `labtrust package-release --profile minimal --out /tmp/labtrust_release` produces MANIFEST.v0.1.json (file hashes), BENCHMARK_CARD.md, metadata.json, results (v0.2 schema), summary.csv/summary.md (leaderboard table), plots, receipts, and FHIR bundles. Use `--seed-base N` for deterministic runs. For a **paper-ready** artifact (baselines + TaskF study + FIGURES/TABLES + receipts): `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>` (see [docs/paper_ready.md](docs/paper_ready.md)).
- **Official baselines**: **v0.2 is canonical.** Frozen results and summary table are in `benchmarks/baselines_official/v0.2/` (see [Benchmark card](docs/benchmark_card.md)). Baseline regression compares against v0.2; v0.1 is legacy. Regenerate with `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force` (matches CI). Compare: `labtrust summarize-results --in benchmarks/baselines_official/v0.2/results/ your_results.json --out /tmp/compare`.
- **How to cite**: This project uses [CITATION.cff](CITATION.cff). You can use [citation-file-format](https://citation-file-format.github.io/) tooling or cite the repository: *LabTrust-Gym: a multi-agent environment for a self-driving hospital lab with a trust skeleton*. https://github.com/fraware/LabTrust-Gym.

## Improvements before going online

Before adding online APIs and non-deterministic runs, see **[docs/IMPROVEMENTS_BEFORE_ONLINE.md](docs/IMPROVEMENTS_BEFORE_ONLINE.md)** for a checklist: stability (ui_fixtures, long tests), **code optimization** (policy loading in hot path, large JSONL, summarize/export), testing (pytest timeout, coverage, CI), documentation, and pre-online readiness.

## Current state

See **docs/STATUS.md** for a detailed report: policy validation, hashchain, tokens, zones, specimens, QC, critical results (v0.2 escalation ladder), catalogue/stability, co-location, queueing, invariant registry, enforcement, **transport** (multi-site), **export** (receipts, FHIR R4), **package-release**, PettingZoo wrappers, scripted/adversary/LLM/MARL baselines, TaskA–TaskF, **quick-eval**, PyPI packaging (`labtrust --version`), studies (run-study, make-plots, reproduce, package-release), and docs site (MkDocs + API reference).

## v0.1.0 release and contract freeze

- **Version:** `labtrust --version` prints v0.1.0 + git SHA. Tag **v0.1.0** from a clean main commit for release.
- **Contract freeze:** [docs/CONTRACTS.md](docs/CONTRACTS.md) lists frozen schemas (runner output, queue, invariant registry, enforcement, receipt, evidence bundle, FHIR, results v0.2 semantics; v0.3 extensible only).
- **Quickstart (paper artifact):** `bash scripts/quickstart_paper_v0_1.sh` (or `scripts/quickstart_paper_v0.1.ps1` on Windows): install → validate-policy → quick-eval → package-release paper_v0.1 → verify-bundle.
- **UI fixtures:** [ui_fixtures/](ui_fixtures/) contains minimal results.v0.2, episode log, evidence bundle, and FHIR bundle for offline UI work. **UI data contract:** [docs/ui_data_contract.md](docs/ui_data_contract.md) specifies ui-export bundle format; the UI depends on `labtrust ui-export` output, not raw internal logs.

## License

Apache-2.0.
