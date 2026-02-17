# Repository structure

Canonical layout of the LabTrust-Gym repo. Keep the root minimal; put CLI and build outputs in `labtrust_runs/` or a path given by `--out`.

## Root (minimal)

| Path | Purpose |
|------|---------|
| `README.md` | Project overview, installation, CLI summary. |
| `LICENSE` | Apache-2.0. |
| `CHANGELOG.md` | Version history. |
| `CONTRIBUTING.md` | Contribution guidelines. |
| `CODE_OF_CONDUCT.md` | Community standards. |
| `CITATION.cff` | Citation metadata. |
| `pyproject.toml` | Package config, dependencies, entry points. |
| `MANIFEST.in` | sdist include/exclude (policy, README, etc.). |
| `Makefile` | Shortcuts: test, lint, format, bench-smoke, policy-validate, **verify** (verification battery), **paper** (requires OUT=; package-release paper_v0.1 then verify-release), **e2e-artifacts-chain** (package-release minimal → export-risk-register → build-release-manifest → verify-release --strict-fingerprints; no network). |
| `mkdocs.yml` | MkDocs site config. |
| `.gitignore` | Ignore build artifacts, venvs, `labtrust_runs/`, root-level CLI outputs. |
| `.github/workflows/` | CI: lint, typecheck, **test** (matrix: ubuntu + Windows, Python 3.11/3.12), **golden** (determinism-report + full suite), policy-validate, **release-fixture-verify** (verify-release --strict-fingerprints on tests/fixtures/release_fixture_minimal), **risk-register-gate**, **risk-coverage-every-pr** (validate-coverage --strict with waivers), **coverage** (every PR), **audit-selfcheck.yml** (Phase A checks), **wheel-smoke.yml** (build wheel, install, validate-policy, quick-eval), **viewer-data-from-release.yml** (path-filtered: build viewer-data/latest from release), **risk-coverage-strict** (schedule/workflow_dispatch); **e2e-artifacts-chain.yml**; **llm_live_optional_smoke.yml** (healthcheck + pack smoke when OPENAI_API_KEY set); **coordination-nightly.yml** (schedule + workflow_dispatch). See [CI](../operations/ci.md). |
| `.gitattributes` | Text/line-ending rules (e.g. `*.sh text eol=lf` so shell scripts use LF on all platforms). |

Do not commit CLI outputs at the root (e.g. `results.json`, `out.json`, `bench_smoke_*.json`). Use `labtrust_runs/` or `--out <path>` so outputs stay out of the repo root.

## Directories

| Directory | Purpose |
|-----------|---------|
| `src/labtrust_gym/` | Main package: engine, envs, baselines, benchmarks, policy loaders, CLI, security, online, export, studies. |
| `policy/` | Versioned policy data and schemas (YAML/JSON). Validated by `labtrust validate-policy`. |
| `policy/schemas/` | JSON schemas for policy files and results (e.g. results.v0.2, risk_registry, coordination_methods, **risk_register_bundle.v0.1**). |
| `policy/risks/` | Risk registry (risk_registry.v0.1.yaml), **waivers.v0.1.yaml** (for validate-coverage --strict), **required_bench_plan.v0.1.yaml** (maps each required_bench cell to evidence: coord_risk or security_suite; used by run_required_bench_matrix scripts). |
| `policy/coordination/` | Coordination method registry, method-risk matrix, coordination study spec, scale_configs, resilience_scoring, injections.v0.2 (red-team injection sets), coordination_security_pack_gate.v0.1 (gate thresholds for internal regression pack). |
| `policy/llm/` | LLM policy: defaults, prompt_registry, model_pricing, action schemas; **llm_fault_model.v0.1.yaml** (deterministic fault injection for llm_offline: invalid_output, empty_output, high_latency, inconsistent_plan). Schema: `policy/schemas/llm_fault_model.v0.1.schema.json`. |
| `policy/safety_case/` | Safety case claims (claims.v0.1.yaml); used by `labtrust safety-case` and package-release. |
| `policy/official/` | Official Benchmark Pack definitions: benchmark_pack.v0.1.yaml (default), benchmark_pack.v0.2.yaml (when `--pipeline-mode llm_live`); used by `labtrust run-official-pack`. |
| `policy/emits/`, `policy/reason_codes/`, `policy/invariants/`, `policy/zones/`, `policy/security/` | Emits vocab, reason codes, invariant registry, zone layout, RBAC, keys, studies, golden (golden_scenarios, prompt_injection_scenarios, security_attack_suite), partners. **policy/security/** includes adversarial_detection.v0.1.yaml and **prompt_injection_defense.v0.1.yaml** (pre-LLM block, sanitizer, output consistency). |
| `policy/coordination_identity_policy.v0.1.yaml`, `policy/tool_boundary_policy.v0.1.yaml`, `policy/memory_policy.v0.1.yaml` | Coordination identity, tool boundary, memory policy (security controls). |
| `benchmarks/` | Baseline registry (baseline_registry.v0.1.yaml), official baselines (v0.1, v0.2). |
| `tests/` | Pytest: golden suite, policy validation, benchmarks, coordination, risk injections, studies, export, etc. |
| `tests/fixtures/` | Test data (coordination study smoke spec, legacy-injection spec, keys; **ui_fixtures/** minimal run dir for UI and risk-register gate; **release_fixture_minimal/** committed release chain for **release-fixture-verify** gate—build with `scripts/build_release_fixture.sh` or `.ps1`; **paper_claims_snapshot/v0.1/** committed snapshot for paper claims regression—update with `scripts/extract_paper_claims_snapshot.py`; **risk_register_bundle_ui_fixtures.v0.1.json** snapshot for risk register contract gate). |
| `examples/` | Example agents and scripts (external_agent_demo, scripted_ops_agent, llm_agent_mock_demo, etc.). |
| `scripts/` | Quickstart and paper-release scripts (shell, PowerShell); **build_release_fixture.sh** and **.ps1** (build tests/fixtures/release_fixture_minimal: package-release minimal → export-risk-register → build-release-manifest → verify-release --strict-fingerprints); **run_required_bench_matrix.sh** and **.ps1** (plan-driven: required_bench_plan.v0.1.yaml + method_risk_matrix → distinct runs → export-risk-register → validate-coverage --strict; default out runs/required_bench_pack); **build_viewer_data_from_release.sh** (package-release minimal, export-risk-register, copy bundle + write viewer-data/latest/latest.json; CI viewer-data-from-release); **build_viewer_data.sh** (build viewer data for risk register); **ci_e2e_artifacts_chain.sh** (e2e reproducible chain: package-release minimal → export-risk-register → build-release-manifest → verify-release --strict-fingerprints; no network); **run_external_reviewer_checks.sh** and **.ps1** (coordination study + coverage gate + COORDINATION_LLM_CARD); **run_external_reviewer_risk_register_checks.sh** and **.ps1** (security/coord smoke or provided dirs, export-risk-register, schema + crosswalk validation); **run_benchmarking_layer1_sanity.sh** / **.ps1**, **run_benchmarking_layer2_coverage.sh** / **.ps1**, **run_benchmarking_layer3_scale.sh** / **.ps1** (three-layer benchmarking matrix; see [Benchmarking plan](../benchmarks/benchmarking_plan.md)). |
| `docs/` | MkDocs source (architecture, systems_and_threat_model, example_experiments, build_your_own_agent, benchmarks, coordination, contracts, getting-started, operations, **paper/** provenance and PAPER_CLAIMS; **ops_runbook.md** operator runbook; **cross_provider_contract.md** cross-provider comparability; etc.). |
| `viewer/` | Risk register viewer: static HTML/JS over RiskRegisterBundle.v0.1; loader (local file, zip, URL, **Load latest release** from viewer-data/latest), search, filters, risk detail, reproduce commands. See [Risk register viewer](../risk-and-security/risk_register_viewer.md). |
| `viewer-data/` | **viewer-data/latest/** holds latest.json and RISK_REGISTER_BUNDLE.v0.1.json built from release (scripts/build_viewer_data_from_release.sh). The **docs** workflow builds site + viewer + viewer-data and deploys to GitHub Pages so the viewer and "Load latest release" are served at the repo Pages URL. |

## Source package (`src/labtrust_gym/`)

| Path | Purpose |
|------|---------|
| `config.py` | Repo root resolution for policy paths. |
| `engine/` | Core env (**state.py** InitialStateDict, **event.py** StepEventDict for reset/step), audit log, zones, specimens, QC, critical, queueing, devices, signatures, RBAC, transport, invariants, enforcement. |
| `coordination/` | Identity (Ed25519 key material, sign/verify), SignedMessageBus (replay protection, epoch binding). |
| `memory/` | Validators (poison/instruction-override detection), store (authenticated writes, TTL, filter on retrieval). |
| `tools/` | Registry, sandbox (egress/data-class limits), execution. |
| `envs/` | PettingZoo Parallel and AEC wrappers. |
| `baselines/` | Scripted ops/runner, adversary, insider, LLM (agent, backends, **fault_model** for llm_offline, signing_proxy, parse_utils), coordination (interface, methods, registry, **adversary_coord**), MARL (PPO: ppo_train with train_config/obs_history_len/reward_scale_schedule, ppo_eval, ppo_agent with train_config.json). |
| `benchmarks/` | Tasks (throughput_sla through coord_risk), runner, metrics, coordination_scale, summarize, determinism_report, **security_runner**, **securitization**, **official_pack**. |
| `policy/` | Loader, validate, invariants_registry, coordination, risks, tokens, prompt_registry, reason_codes, emits. |
| `security/` | Risk injections, secret_scrubber, fs_safety, output_shaping, adversarial_detection, **prompt_injection_defense** (pre-LLM check, output consistency), agent_capabilities, **safety_case**. |
| `studies/` | study_runner, coordination_study_runner, **coordination_security_pack** (internal regression pack: fixed scale × method × injection, pack_results/, pack_summary.csv, pack_gate.md), **coordination_summarizer** (SOTA leaderboard per method, method-class comparison; study runner writes summary/sota_leaderboard.csv, sota_leaderboard.md, method_class_comparison.csv, method_class_comparison.md; CLI `labtrust summarize-coordination`), coverage_gate, plots, reproduce, package_release. |
| `export/` | Receipts, **FHIR R4** (valid HL7 R4: data-absent-reason for missing specimen/value; no placeholder IDs), ui_export, **risk_register_bundle** (RiskRegisterBundle.v0.1 from policy + run dirs; evidence gaps status=missing first-class), **validate_coverage** (coverage validation; use `labtrust validate-coverage --strict` to fail on missing evidence), verify (including optional policy fingerprints). |
| `online/` | HTTP server, authz, rate limit, telemetry. |
| `runner/` | Golden runner, adapter, emits validator. |
| `logging/` | Episode log. |
| `cli/` | Main CLI (validate-policy, run-benchmark, quick-eval, run-study, run-coordination-study, make-plots, etc.). |

## Where to put outputs

- **Benchmark results**: `labtrust run-benchmark ... --out labtrust_runs/bench/results.json` or use default `labtrust_runs/` for quick-eval.
- **Study outputs**: `labtrust run-study --out labtrust_runs/study_001` or `labtrust run-coordination-study --out labtrust_runs/coord_001`.
- **Plots**: `labtrust make-plots --run labtrust_runs/study_001` writes into that run’s `figures/` subdir.
- **Release artifact**: `labtrust package-release --out /tmp/labtrust_release` (outside repo). Then `export-risk-register` into that dir, `build-release-manifest` (writes RELEASE_MANIFEST.v0.1.json), and `verify-release --strict-fingerprints`. Paper profile (`--profile paper_v0.1`) also writes **SECURITY/** (attack_results.json, coverage, reason_codes, deps_inventory) and **SAFETY_CASE/** (safety_case.json, safety_case.md).
- **Security suite**: `labtrust run-security-suite --out <dir>` writes SECURITY/ under the given directory.
- **Coordination security pack**: `labtrust run-coordination-security-pack --out <dir>` writes pack_results/, pack_summary.csv, pack_gate.md (internal regression; see [Security attack suite](../risk-and-security/security_attack_suite.md#coordination-security-pack-internal-regression)).
- **Safety case**: `labtrust safety-case --out <dir>` writes SAFETY_CASE/safety_case.json and safety_case.md under the given directory.
- **Official pack**: `labtrust run-official-pack --out <dir> [--pipeline-mode llm_live] [--allow-network]` writes a single output tree (baselines/, SECURITY/, SAFETY_CASE/, transparency log, etc.) for the Official Benchmark Pack (v0.1 or v0.2 when llm_live). With llm_live, also writes TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json.
- **Risk register bundle**: `labtrust export-risk-register --out <dir>` writes `<dir>/RISK_REGISTER_BUNDLE.v0.1.json` from policy and optional run dirs (evidence gaps as status=missing); use `--runs <dir_or_glob>` and `--include-official-pack <dir>` to add evidence; `--inject-ui-export` copies the bundle into each run dir. **Coverage gate:** `labtrust validate-coverage [--bundle <path>] [--out <dir>] --strict` validates required_bench coverage and exits 1 if any required risk has missing evidence. See [Risk register](../risk-and-security/risk_register.md), [Risk register contract](../contracts/risk_register_contract.v0.1.md).

The directory `labtrust_runs/` is gitignored. Do not commit root-level `results.json`, `out.json`, `bench_smoke_*.json`, `ep.jsonl`, `quick_eval_*/`, or `ui_bundle.zip`; they are ignored so the root stays clean.
