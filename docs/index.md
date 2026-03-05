# LabTrust-Gym

A multi-agent environment (PettingZoo/Gym style) for hospital lab automation, with a reference **trust skeleton**: RBAC, signed actions, append-only audit log, invariants, and anomaly throttles. The first instance models a **pathology lab**—specifically a **blood sciences** lane (specimen reception through release and multi-site transport). See [Glossary – Lab terminology](reference/glossary.md#lab-terminology-hospital-lab-pathology-lab-blood-sciences-lab).

This documentation reflects the **current state of the repo**: contract freeze, coordination suite (coord_scale/coord_risk, methods including **consensus_paxos_lite**, **swarm_stigmergy_priority**, risk injections, study runner), ui-export, paper-ready release, systems and threat model, example experiments, build-your-own-agent walkthrough, prompt-injection defense (pre-LLM block, output consistency), PPO/MARL (train_config, obs_history_len, Optuna HPO, train_config.json), valid FHIR R4 export (data-absent-reason for missing specimen/value; no placeholder IDs), risk register with evidence gaps as first-class and **validate-coverage --strict**. **Hospital lab full pipeline:** `scripts/run_hospital_lab_full_pipeline.py` orchestrates cross-provider pack, optional coordination pack, security (smoke/full), method sweep; loads `.env` from repo root for API keys. **LLM backend check:** `scripts/check_llm_backends_live.py` (openai_live/anthropic_live) loads `.env`; use for zero-throughput debugging. **Coordination pack:** `labtrust run-coordination-security-pack` supports `--matrix-preset hospital_lab`, `--scale-ids small_smoke`, `--workers N`, `--llm-backend openai_live|anthropic_live` (requires `--allow-network`). **PettingZoo env:** LabTrustParallelEnv and **LabTrustVectorEnv** (N envs, synchronous reset/step); render(), step_batch(events), batch get_agent_zones/get_agent_roles, reset(options) with timing_mode and dt_s, FlattenObsWrapper; see [PettingZoo API](agents/pettingzoo_api.md). **Run summary and persistence:** `labtrust run-summary --run <dir>` for one-line stats; `--log-step-interval N` writes steps.jsonl; `--checkpoint-every N` and `--checkpoint-every-steps N` with `--resume-from` for episode and step-level checkpoint/resume. **Debate:** optional LLM aggregator when `coord_debate_aggregator: llm` and aggregator backend configured; fallback to majority. **Injectors:** inj_prompt_injection and inj_misparam_device implemented; five reserved IDs remain NoOp. **Evidence:** risk-coverage-pr runs two R-SYS-001 cells (centralized_planner, swarm_reactive + INJ-DOS-PLANNER-001) for real evidence; release workflow has optional live-llm-smoke job when OPENAI_API_KEY is set. **Scale and security:** parallel multi-agentic backend, shared TokenBucket rate limiter, round_timeout_s and max_workers; scale-capable methods with per-agent LLM when N > N_max; security suite and coord_pack gate; optional `--use-full-driver-loop` for run-security-suite. **Unit of truth:** release artifact chain; committed fixture at **tests/fixtures/release_fixture_minimal** (build with scripts/build_release_fixture); **required-bench coverage pack** via plan-driven scripts/run_required_bench_matrix (policy/risks/required_bench_plan.v0.1.yaml); **viewer** and **viewer-data/latest** on GitHub Pages (docs workflow builds site + viewer + viewer-data and deploys); "Load latest release" fetches viewer-data/latest. **Paper claims regression:** committed snapshot at tests/fixtures/paper_claims_snapshot/v0.1, extract script, compare logic, CI job on schedule/workflow_dispatch; see [Paper claims](benchmarks/PAPER_CLAIMS.md). CI runs on every PR: test matrix (Ubuntu + Windows, Python 3.11/3.12), golden job (determinism-report + determinism budget + full golden suite), **release-fixture-verify** (verify-release --strict-fingerprints on committed fixture), **risk-coverage-every-pr**, **coverage** (ratchet/fail_under); **e2e-artifacts-chain** (package-release → export-risk-register → build-release-manifest → verify-release --strict-fingerprints); **viewer-data-from-release** (path-filtered); optional **llm_live_optional_smoke** asserts model/latency/cost when OPENAI_API_KEY is set. **summarize-results** uses streaming (bounded memory). **Uncertainty quantification:** rate CIs (Clopper-Pearson), detector and LLM calibration (ECE/MCE), robust Pareto dominance, epistemic/aleatoric mapping; uncertainty columns appear in summary_v0.3.csv, summary_coord.csv, pack_summary.csv, and SECURITY/coordination_risk_matrix ([Uncertainty quantification](benchmarks/uncertainty_quantification.md), [Metrics contract – Uncertainty in standard reports](contracts/metrics_contract.md#uncertainty-metrics-in-standard-reports)). Release verification: **verify-release** (EvidenceBundles + risk register + RELEASE_MANIFEST), **build-release-manifest**. Dedicated error types in **labtrust_gym.errors** (LabTrustError, PolicyLoadError, PolicyPathError); policy path resolution raises PolicyPathError when policy dir not found or LABTRUST_POLICY_DIR invalid. **Paper provenance** ([paper/README](benchmarks/paper/README.md)), **LLM coordination standards-of-excellence** ([Live LLM](agents/llm_live.md)), engine **state.py** / **event.py** (InitialStateDict, StepEventDict), and all CLI commands. Use the nav (left) or [Getting started](getting-started/index.md) to begin. See [Repository structure](reference/repository_structure.md), [Frozen contracts](contracts/frozen_contracts.md), [UI data contract](contracts/ui_data_contract.md), and [CI](operations/ci.md) for details.

## North star

- **Environment**: Pip-installable, standard multi-agent API (PettingZoo AEC or parallel).
- **Trust skeleton**: Roles/permissions, signed actions, hash-chained audit log, invariants, reason codes.
- **Benchmarks**: Tasks and baselines (scripted, MARL, LLM) with clear safety/throughput trade-offs.

## Principles

- **Golden scenarios drive development**: The simulator is correct when the golden suite passes.
- **Policy is data**: Invariants, tokens, reason codes, catalogue, zones live in versioned files under `policy/`.
- **Determinism**: Golden runs are deterministic (seeded RNG, no ambient randomness).
- **No silent failure**: Missing hooks or invalid data fail loudly with reason codes.

## Quick start

```bash
git clone https://github.com/fraware/LabTrust-Gym.git
cd LabTrust-Gym
pip install -e ".[dev]"
labtrust validate-policy
pytest -q
```

With PettingZoo, benchmarks, and plots:

```bash
pip install -e ".[dev,env,plots]"
LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q
labtrust run-benchmark --task throughput_sla --episodes 5 --seed 42 --out results.json
labtrust reproduce --profile minimal
```

Optional extras: `.[env]` (PettingZoo/Gymnasium), `.[plots]` (matplotlib), `.[marl]` (Stable-Baselines3), `.[docs]` (MkDocs + mkdocstrings), `.[llm_openai]` (OpenAI live backend), `.[llm_anthropic]` (Anthropic live backend). From repo root: **`make verify`** runs the full verification battery; **`make paper OUT=<dir>`** builds a paper-ready artifact (package-release paper_v0.1 then verify-release).

## CLI summary

| Command | Description |
|---------|-------------|
| `--version` / `-V` | Print version and git SHA |
| `validate-policy` | Validate all policy files against JSON schemas |
| `quick-eval` | 1 episode each of throughput_sla, adversarial_disruption, multi_site_stat; markdown summary and logs under `./labtrust_runs/` |
| `run-benchmark` | Run throughput_sla through coord_risk; write results.json. For coord_scale/coord_risk use `--coord-method`, for coord_risk add `--injection`. Optional `--scale` (small_smoke, medium_stress_signed_bus, corridor_heavy), `--timing` (explicit | simulated), `--llm-backend`, `--llm-model`, `--llm-agents` (see [Live LLM](agents/llm_live.md)). Agent-centric: `--agent-driven` (single), `--multi-agentic` (N agents + combine); `--use-parallel-multi-agentic` with scale + LLM uses ParallelMultiAgenticBackend (configurable round_timeout_s, max_workers; see [Scale operational limits](benchmarks/scale_operational_limits.md)). Scale-capable methods (those with `scale_capable: true` in policy, see [design_choices §6.3](architecture/design_choices.md)) get per-agent LLM when N > N_max. |
| `eval-agent` | Run benchmark with external agent (module:Class or module:function); write results.json (v0.2) |
| `bench-smoke` | 1 episode per task (throughput_sla, stat_insertion, qc_cascade) |
| `run-study` | Run study from spec (ablations → conditions) |
| `run-coordination-study` | Run coordination study (scale × method × injection); cells, summary_coord.csv, pareto.md, sota_leaderboard (main + full), method_class_comparison. Use `--llm-backend deterministic` for offline. External reviewer: `run_external_reviewer_checks.sh`; risk register: `run_external_reviewer_risk_register_checks.sh`. See [Coordination studies](coordination/coordination_studies.md), [Risk register](risk-and-security/risk_register.md), [LLM Coordination Protocol](benchmarks/llm_coordination_protocol.md). |
| `run-coordination-security-pack` | Run internal coordination security regression pack: scale × method × injection matrix. Use `--matrix-preset hospital_lab`, optional `--scale-ids small_smoke`, `--workers N`, `--llm-backend openai_live|anthropic_live` (requires `--allow-network`). Writes pack_results/, pack_summary.csv, pack_gate.md. See [Security attack suite](risk-and-security/security_attack_suite.md#coordination-security-pack-internal-regression). |
| `summarize-coordination` | Aggregate coordination results: read summary_coord.csv or pack_summary.csv from `--in`, write SOTA leaderboard (main + full) and method-class comparison to `--out/summary/`. Main table: key metrics + run metadata when pack_manifest.json present; full table: all numeric aggregates. See [Coordination studies](coordination/coordination_studies.md), [Hospital lab key metrics](benchmarks/hospital_lab_metrics.md). |
| `recommend-coordination-method` | Produce COORDINATION_DECISION.v0.1.json and COORDINATION_DECISION.md from run dir (`--run`, `--out`). |
| `build-coordination-matrix` | Build CoordinationMatrix v0.1 from llm_live coordination run dir (`--run`, `--out`). |
| `make-plots` | Generate figures and data tables from a study run (`--run \<dir\>`; optional `--theme light\|dark`). Produces Pareto scatters, bar charts, throughput box by condition, metrics overview; for coordination runs adds resilience vs p95_tat and attack_success_rate bar. See [Studies and plots](benchmarks/studies.md). |
| `reproduce --profile minimal \| full` | Reproduce minimal results + figures (throughput_sla & qc_cascade sweep + plots) |
| `export-receipts --run \<log\> --out \<dir\>` | Export Receipt.v0.1 and EvidenceBundle.v0.1 from episode log |
| `export-fhir --receipts \<dir\> --out \<dir\>` | Export valid HL7 FHIR R4 Bundle from receipts directory (data-absent-reason for missing specimen/value; no placeholder IDs). See [FHIR R4 export](export/fhir_export.md). |
| `validate-fhir --bundle \<path\> --terminology \<path\> [--strict]` | Validate FHIR bundle coded elements (e.g. Observation.code, interpretation) against a value set; optional extension, not part of minimal benchmark. See [FHIR R4 export](export/fhir_export.md). |
| `verify-bundle --bundle \<dir\> [--strict-fingerprints]` | Verify EvidenceBundle.v0.1: manifest, schema, hashchain, invariant trace; optional policy fingerprints (tool, rbac, coordination, memory). Use --strict-fingerprints for release validation. |
| `verify-release --release-dir \<dir\> [--strict-fingerprints]` | Full release verification: EvidenceBundles, risk register (schema + crosswalk), RELEASE_MANIFEST hashes. E2E chain: package-release → export-risk-register → build-release-manifest → verify-release. See [Trust verification](risk-and-security/trust_verification.md). |
| `build-release-manifest --release-dir \<dir\> --out \<path\>` | Write RELEASE_MANIFEST.v0.1.json (hashes of MANIFEST, evidence bundles, risk register). Then verify-release validates offline. |
| `run-security-suite --out \<dir\>` | Run security attack suite; emit SECURITY/attack_results.json and securitization packet ([Security attack suite](risk-and-security/security_attack_suite.md)). Optional `--agent-driven-mode single | multi_agentic` (scenario_ref and llm_attacker entry points), `--use-full-driver-loop` (full driver loop for agent-driven when set). coord_pack_ref with N > N_max exercises simulation-centric combine path. See Coverage by workflow and Step semantics in that doc. |
| `safety-case --out \<dir\>` | Generate safety case (claim to control, test, artifact, command) to SAFETY_CASE/safety_case.json and .md |
| `run-official-pack --out \<dir\> [--seed-base N] [--pipeline-mode llm_live] [--allow-network] [--llm-backend \<backend\>]` | Run Official Benchmark Pack (v0.1 default, v0.2 when `--pipeline-mode llm_live`); single output dir with baselines, SECURITY/, SAFETY_CASE/, transparency log; llm_live adds TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json ([Official benchmark pack](benchmarks/official_benchmark_pack.md)) |
| `run-cross-provider-pack --out \<dir\> --providers \<list\>` | Run official pack once per provider (llm_live); per-provider dirs plus summary_cross_provider.json/.md ([Official benchmark pack](benchmarks/official_benchmark_pack.md), [Live LLM](agents/llm_live.md)) |
| `llm-healthcheck --backend \<openai_responses\|openai_live\|anthropic_live\|ollama_live\> [--allow-network]` | One minimal request to live backend; reports ok, model_id, latency_ms ([Live LLM](agents/llm_live.md)) |
| `ui-export --run \<dir\> --out \<zip\>` | Export UI-ready zip (index, events, receipts_index, reason_codes) from run dir; see [UI data contract](contracts/ui_data_contract.md) |
| `export-risk-register --out \<dir\> [--runs \<dir_or_glob\> ...]` | Export RiskRegisterBundle.v0.1 into \<dir\>/RISK_REGISTER_BUNDLE.v0.1.json. Evidence gaps (status=missing) are first-class. CI runs contract gate (schema, snapshot, crosswalk, coverage). Optional `--include-official-pack \<dir\>`, `--inject-ui-export`. See [Risk register](risk-and-security/risk_register.md), [Risk register contract](contracts/risk_register_contract.v0.1.md). |
| `build-risk-register-bundle --out \<path\> [--run \<dir\> ...]` | Build same bundle to an explicit file path (alternative to export-risk-register). |
| `validate-coverage [--bundle \<path\>] [--out \<dir\>] [--strict]` | Validate risk register bundle coverage (required_bench evidenced or waived). With `--strict`, loads waivers from policy/risks/waivers.v0.1.yaml; exit 1 if any required risk has missing evidence and is not waived. |
| `audit-selfcheck --out \<dir\>` | Run Phase A audit checks plus doctor-style checks (Python path, venv, extras, filesystem, policy); write AUDIT_SELF_CHECK.json with `checks[]`. Exit non-zero if any required check fails. CI: audit-selfcheck.yml; wheel-smoke runs it after install. |
| `package-release --profile minimal \| full \| paper_v0.1 --out \<dir\>` | Release candidate: minimal/full = reproduce + receipts + FHIR + plots; paper_v0.1 = baselines + insider_key_misuse study + FIGURES/TABLES + receipts + SECURITY/ + COORDINATION_CARD.md + COORDINATION_LLM_CARD.md. See [Paper provenance](benchmarks/paper/README.md). |
| `generate-official-baselines --out \<dir\>` | Run Tasks A–F with official baselines; write results/, summary, metadata (--episodes, --seed, --force) |
| `summarize-results --in \<paths\> --out \<dir\>` | Stream results (bounded memory); write summary_v0.2.csv (CI-stable), summary_v0.3.csv (paper-grade), summary.csv + summary.md. When any result has run metadata, also writes run_info.csv and adds a Run info section to summary.md. |
| `run-summary --run \<dir\> [--format text \| json]` | One-line stats (episodes, steps, violations, throughput) for a run directory (results.json or episodes.jsonl). See [Scale operational limits](benchmarks/scale_operational_limits.md). |
| `determinism-report` | Run benchmark twice; produce determinism_report.md (checks summary, run config, result, hash comparison) and determinism_report.json; assert v0.2 metrics and log hash identical |
| `train-ppo`, `eval-ppo` | PPO training/eval (requires `.[marl]`). Training accepts `train_config` (net_arch, learning_rate, n_steps, obs_history_len, reward_scale_schedule) and writes `train_config.json`; eval-ppo auto-loads it from the model dir. Optional HPO: `.[marl_hpo]` for Optuna. Use `eval-agent` with `labtrust_gym.baselines.marl.ppo_agent:PPOAgent` and `LABTRUST_PPO_MODEL` to run benchmark with a trained model (PPOAgent loads device_ids and obs_history_len from train_config.json). See [MARL baselines](agents/marl_baselines.md). |

## Layout

See [Repository structure](reference/repository_structure.md) for the full directory layout and where to put CLI outputs.

| Path | Description |
|------|-------------|
| `policy/` | Versioned YAML/JSON: schemas, emits, invariants (v1.0), tokens, reason_codes, zones, sites, catalogue, stability, equipment, critical, enforcement, studies, **risks** (risk_registry), **coordination** (methods, method_risk_matrix, coordination_study_spec, scale_configs, injections.v0.2, coordination_security_pack_gate), **safety_case** (claims.v0.1), **official** (benchmark_pack.v0.1, benchmark_pack.v0.2 for llm_live), **llm** (llm_fault_model.v0.1, defaults, prompt_registry), golden, partners. Validated by `labtrust validate-policy`. |
| `src/labtrust_gym/` | Package: config, engine/, coordination/ (identity, bus), memory/ (validators, store), tools/ (registry, sandbox), envs/ (PettingZoo), baselines/ (scripted, adversary, llm (fault_model for llm_offline), coordination, adversary_coord, marl), benchmarks/ (tasks throughput_sla through coord_risk, runner, coordination_scale, metrics, summarize, security_runner, securitization, official_pack), policy/, security/ (safety_case, risk_injections, …), studies/ (study_runner, coordination_study_runner, coordination_security_pack, plots, reproduce, package_release), export/, online/, runner/, logging/, cli/. |
| `tests/` | Pytest: golden suite, policy validation, benchmarks, **coordination** (scale, methods, study, policy), **risk_injections**, **risk register** (bundle, contract gate: schema, snapshot, crosswalk, coverage), studies, export, online, etc. |
| `docs/` | MkDocs source: [Getting started](getting-started/index.md), [Architecture](architecture/index.md), [Policy](policy/index.md), [Coordination](coordination/index.md), [Benchmarks](benchmarks/index.md), [Contracts](contracts/index.md), [Risk and security](risk-and-security/index.md), [Export](export/index.md), [Agents](agents/index.md), [Operations](operations/index.md), [Reference](reference/index.md). |

## What's frozen

Contracts and schema versions that define correctness (anti-regression backbone): **[Frozen contracts](contracts/frozen_contracts.md)** — runner output contract, queue contract (v0.1), invariant registry schema (v1.0), enforcement map schema (v0.1), study spec schema (v0.1).

## Documentation structure

| Section | Description |
|--------|-------------|
| [Getting started](getting-started/index.md) | Installation, build your own agent, example agents, forker guide, [Quick demos](getting-started/quick_demos.md), troubleshooting. |
| [Trust verification](risk-and-security/trust_verification.md) | Verification chain, EvidenceBundles, risk register coverage, and artifact-to-concern mapping; what each step proves and how to run or inspect it. |
| [Use cases and impact](reference/use_cases_and_impact.md) | Task and pack mapping to high-impact lab operations; capability metrics. |
| [Architecture](architecture/index.md) | [System overview](architecture/system_overview.md) (how the pieces fit together), system design, threat model, diagrams, workflow spec. |
| [Policy](policy/index.md) | Policy pack, coordination policy, invariants, enforcement. |
| [Coordination](coordination/index.md) | Methods, scale, matrix, studies, benchmark card. |
| [Benchmarks](benchmarks/index.md) | Tasks, cards, official pack, studies, uncertainty quantification, reproduce, paper. |
| [Contracts](contracts/index.md) | Frozen contracts, UI data, risk register, queue, CLI, metrics. |
| [Risk and security](risk-and-security/index.md) | Risk register, viewer, injections, security suite, controls. |
| [Export](export/index.md) | FHIR R4 export and verification. |
| [Agents](agents/index.md) | LLM and MARL baselines, PettingZoo API, extension development. |
| [Operations](operations/index.md) | CI, release checklist, ops runbook, how-to guides. |
| [Reference](reference/index.md) | Repository structure, lab profile, observability, testing. |
| [API Reference](api/index.md) | Auto-generated API docs. |
