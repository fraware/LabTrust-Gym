# LabTrust-Gym

A multi-agent environment (PettingZoo/Gym style) for a self-driving hospital lab, with a reference **trust skeleton**: RBAC, signed actions, append-only audit log, invariants, and anomaly throttles.

This documentation reflects the **current state of the repo**: contract freeze, coordination suite (coord_scale/coord_risk, methods, risk injections, study runner), ui-export, paper-ready release, and all CLI commands. Use the nav (left) or [Installation](installation.md) to get started. See [Repository structure](repository_structure.md) for directory layout and [Frozen contracts](frozen_contracts.md) and [UI data contract](ui_data_contract.md) for stable interfaces.

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

Optional extras: `.[env]` (PettingZoo/Gymnasium), `.[plots]` (matplotlib), `.[marl]` (Stable-Baselines3), `.[docs]` (MkDocs + mkdocstrings), `.[llm_openai]` (OpenAI live backend), `.[llm_anthropic]` (Anthropic live backend).

## CLI summary

| Command | Description |
|---------|-------------|
| `--version` / `-V` | Print version and git SHA |
| `validate-policy` | Validate all policy files against JSON schemas |
| `quick-eval` | 1 episode each of throughput_sla, adversarial_disruption, multi_site_stat; markdown summary and logs under `./labtrust_runs/` |
| `run-benchmark` | Run throughput_sla through coord_risk; write results.json. For coord_scale/coord_risk use `--coord-method`, for coord_risk add `--injection`. Optional `--scale` (small_smoke, medium_stress_signed_bus, corridor_heavy), `--timing` (explicit | simulated), `--llm-backend`, `--llm-model`, `--llm-agents` (see [Live LLM](llm_live.md)) |
| `eval-agent` | Run benchmark with external agent (module:Class or module:function); write results.json (v0.2) |
| `bench-smoke` | 1 episode per task (throughput_sla, stat_insertion, qc_cascade) |
| `run-study` | Run study from spec (ablations → conditions) |
| `run-coordination-study` | Run coordination study (scale × method × injection); cells, summary_coord.csv, pareto.md, sota_leaderboard, method_class_comparison. Use `--llm-backend deterministic` for offline. External reviewer: `run_external_reviewer_checks.sh`; risk register: `run_external_reviewer_risk_register_checks.sh`. See [Coordination studies](coordination_studies.md), [Risk register](risk_register.md), [LLM Coordination Protocol](llm_coordination_protocol.md). |
| `run-coordination-security-pack` | Run internal coordination security regression pack: fixed scale × method × injection matrix (deterministic, 1 ep/cell). Writes pack_results/, pack_summary.csv, pack_gate.md. See [Security attack suite](security_attack_suite.md#coordination-security-pack-internal-regression). |
| `summarize-coordination` | Aggregate coordination results: read summary_coord.csv from `--in`, write SOTA leaderboard and method-class comparison to `--out`. See [Coordination studies](coordination_studies.md). |
| `recommend-coordination-method` | Produce COORDINATION_DECISION.v0.1.json and COORDINATION_DECISION.md from run dir (`--run`, `--out`). |
| `build-coordination-matrix` | Build CoordinationMatrix v0.1 from llm_live coordination run dir (`--run`, `--out`). |
| `make-plots` | Generate figures and data tables from a study run; for coordination runs adds resilience vs p95_tat and attack_success_rate bar |
| `reproduce --profile minimal \| full` | Reproduce minimal results + figures (throughput_sla & qc_cascade sweep + plots) |
| `export-receipts --run \<log\> --out \<dir\>` | Export Receipt.v0.1 and EvidenceBundle.v0.1 from episode log |
| `export-fhir --receipts \<dir\> --out \<dir\>` | Export FHIR R4 Bundle from receipts directory |
| `verify-bundle --bundle \<dir\>` | Verify EvidenceBundle.v0.1: manifest, schema, hashchain, invariant trace; optional policy fingerprints (tool, rbac, coordination, memory) |
| `run-security-suite --out \<dir\>` | Run security attack suite; emit SECURITY/attack_results.json and securitization packet ([Security attack suite](security_attack_suite.md)) |
| `safety-case --out \<dir\>` | Generate safety case (claim to control, test, artifact, command) to SAFETY_CASE/safety_case.json and .md ([Implementation verification](implementation_verification.md)) |
| `run-official-pack --out \<dir\> [--seed-base N] [--pipeline-mode llm_live] [--allow-network] [--llm-backend \<backend\>]` | Run Official Benchmark Pack (v0.1 default, v0.2 when `--pipeline-mode llm_live`); single output dir with baselines, SECURITY/, SAFETY_CASE/, transparency log; llm_live adds TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json ([Official benchmark pack](official_benchmark_pack.md)) |
| `run-cross-provider-pack --out \<dir\> --providers \<list\>` | Run official pack once per provider (llm_live); per-provider dirs plus summary_cross_provider.json/.md ([Official benchmark pack](official_benchmark_pack.md), [Live LLM](llm_live.md)) |
| `llm-healthcheck --backend \<openai_responses\|openai_live\|anthropic_live\> [--allow-network]` | One minimal request to live backend; reports ok, model_id, latency_ms ([Live LLM](llm_live.md)) |
| `ui-export --run \<dir\> --out \<zip\>` | Export UI-ready zip (index, events, receipts_index, reason_codes) from run dir; see [UI data contract](ui_data_contract.md) |
| `export-risk-register --out \<dir\> [--runs \<dir_or_glob\> ...]` | Export RiskRegisterBundle.v0.1 into \<dir\>/RISK_REGISTER_BUNDLE.v0.1.json. Evidence from SECURITY/, summary/, PARETO/, SAFETY_CASE/, MANIFEST in run dirs. CI runs contract gate (schema, snapshot, crosswalk, coverage). Optional `--include-official-pack \<dir\>`, `--inject-ui-export`. See [Risk register](risk_register.md), [Risk register contract](risk_register_contract.v0.1.md). |
| `build-risk-register-bundle --out \<path\> [--run \<dir\> ...]` | Build same bundle to an explicit file path (alternative to export-risk-register). |
| `package-release --profile minimal \| full \| paper_v0.1 --out \<dir\>` | Release candidate: minimal/full = reproduce + receipts + FHIR + plots; paper_v0.1 = baselines + insider_key_misuse study + FIGURES/TABLES + receipts + SECURITY/ + COORDINATION_CARD.md + COORDINATION_LLM_CARD.md ([paper_ready](paper_ready.md)) |
| `generate-official-baselines --out \<dir\>` | Run Tasks A–F with official baselines; write results/, summary, metadata (--episodes, --seed, --force) |
| `summarize-results --in \<paths\> --out \<dir\>` | Aggregate results.json; write summary_v0.2.csv (CI-stable), summary_v0.3.csv (paper-grade), summary.csv + summary.md |
| `determinism-report` | Run benchmark twice; produce determinism_report.md/.json; assert v0.2 metrics and log hash identical |
| `train-ppo`, `eval-ppo` | PPO training/eval (requires `.[marl]`) |

## Layout

See [Repository structure](repository_structure.md) for the full directory layout and where to put CLI outputs.

| Path | Description |
|------|-------------|
| `policy/` | Versioned YAML/JSON: schemas, emits, invariants (v1.0), tokens, reason_codes, zones, sites, catalogue, stability, equipment, critical, enforcement, studies, **risks** (risk_registry), **coordination** (methods, method_risk_matrix, coordination_study_spec, scale_configs, injections.v0.2, coordination_security_pack_gate), **safety_case** (claims.v0.1), **official** (benchmark_pack.v0.1, benchmark_pack.v0.2 for llm_live), **llm** (llm_fault_model.v0.1, defaults, prompt_registry), golden, partners. Validated by `labtrust validate-policy`. |
| `src/labtrust_gym/` | Package: config, engine/, coordination/ (identity, bus), memory/ (validators, store), tools/ (registry, sandbox), envs/ (PettingZoo), baselines/ (scripted, adversary, llm (fault_model for llm_offline), coordination, adversary_coord, marl), benchmarks/ (tasks throughput_sla through coord_risk, runner, coordination_scale, metrics, summarize, security_runner, securitization, official_pack), policy/, security/ (safety_case, risk_injections, …), studies/ (study_runner, coordination_study_runner, coordination_security_pack, plots, reproduce, package_release), export/, online/, runner/, logging/, cli/. |
| `tests/` | Pytest: golden suite, policy validation, benchmarks, **coordination** (scale, methods, study, policy), **risk_injections**, **risk register** (bundle, contract gate: schema, snapshot, crosswalk, coverage), studies, export, online, etc. |
| `docs/` | MkDocs source: architecture, benchmarks, coordination (methods, scale, studies, policy, checklist), contracts, **risk_register** (bundle, generate, review), installation, repository_structure, STATUS. |

## What's frozen

Contracts and schema versions that define correctness (anti-regression backbone): **[Frozen contracts](frozen_contracts.md)** — runner output contract, queue contract (v0.1), invariant registry schema (v1.0), enforcement map schema (v0.1), study spec schema (v0.1).

## See also

- [Installation](installation.md) — pip, quick-eval, quickstart script, troubleshooting
- [Architecture](architecture.md)
- [Policy pack and schemas](policy_pack.md)
- [Frozen contracts](frozen_contracts.md) (public contract freeze v0.1.0)
- [UI data contract](ui_data_contract.md) — ui-export bundle format; UI consumes ui-export output, not raw logs
- [Risk register](risk_register.md) — Bundle overview; generate from fixtures, paper release, or official pack; review coverage and external reviewer script
- [Risk register contract](risk_register_contract.v0.1.md) — RiskRegisterBundle.v0.1 format; build with `export-risk-register` or `build-risk-register-bundle`
- [Risk register viewer](risk_register_viewer.md) — Dataset-driven viewer (loader: local file, zip, URL); search, filters, risk detail, reproduce commands
- [Invariants and enforcement](invariants_registry.md) · [Enforcement](enforcement.md)
- [PettingZoo API](pettingzoo_api.md)
- [Benchmarks](benchmarks.md) · [Benchmark card](benchmark_card.md) · [Coordination benchmark card](coordination_benchmark_card.md) (coord_scale/coord_risk) · [Benchmarking plan](benchmarking_plan.md) (three-layer matrix: sanity, coverage, scale) · [LLM Coordination Protocol](llm_coordination_protocol.md) · [Official benchmark pack](official_benchmark_pack.md) · [Studies and plots](studies.md) · [Reproduce](reproduce.md) · [Paper-ready release](paper_ready.md) (coordination checklists: [Coordination methods](coordination_methods.md))
- [FHIR R4 export](fhir_export.md) · [Evidence verification](evidence_verification.md) · [Security attack suite and securitization packet](security_attack_suite.md) · [Implementation verification](implementation_verification.md) (safety case, controls, artifacts)
- [MARL baselines](marl_baselines.md) · [LLM baselines](llm_baselines.md) · [Live LLM benchmark mode](llm_live.md)
- [Security controls for online mode](security_online.md) · [Deployment hardening](deployment_hardening.md) (B008) · [Output controls](output_controls.md) (B009)
- [CI](ci.md) · [STATUS](STATUS.md) (includes 3-min summary)
- [STATUS](STATUS.md) — [Implementation and testing audit](STATUS.md#implementation-and-testing-audit) (official pack v0.2, llm_live); [Improvements before online](STATUS.md#improvements-before-online-checklist) (stability, code, testing, docs)
- [API Reference](api/index.md) (auto-generated)
