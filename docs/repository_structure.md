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
| `Makefile` | Shortcuts: test, lint, format, bench-smoke, policy-validate. |
| `mkdocs.yml` | MkDocs site config. |
| `.gitignore` | Ignore build artifacts, venvs, `labtrust_runs/`, root-level CLI outputs. |
| `.github/workflows/` | CI: lint, typecheck, test, policy-validate, bench-smoke, coordination-smoke, quick-eval, docs. |

Do not commit CLI outputs at the root (e.g. `results.json`, `out.json`, `bench_smoke_*.json`). Use `labtrust_runs/` or `--out <path>` so outputs stay out of the repo root.

## Directories

| Directory | Purpose |
|-----------|---------|
| `src/labtrust_gym/` | Main package: engine, envs, baselines, benchmarks, policy loaders, CLI, security, online, export, studies. |
| `policy/` | Versioned policy data and schemas (YAML/JSON). Validated by `labtrust validate-policy`. |
| `policy/schemas/` | JSON schemas for policy files and results (e.g. results.v0.2, risk_registry, coordination_methods). |
| `policy/risks/` | Risk registry (risk_registry.v0.1.yaml). |
| `policy/coordination/` | Coordination method registry, method-risk matrix, coordination study spec, scale_configs, resilience_scoring, injections.v0.2 (red-team injection sets). |
| `policy/safety_case/` | Safety case claims (claims.v0.1.yaml); used by `labtrust safety-case` and package-release. |
| `policy/official/` | Official Benchmark Pack definition (benchmark_pack.v0.1.yaml); used by `labtrust run-official-pack`. |
| `policy/emits/`, `policy/reason_codes/`, `policy/invariants/`, `policy/zones/`, etc. | Emits vocab, reason codes, invariant registry, zone layout, RBAC, keys, studies, golden (golden_scenarios, prompt_injection_scenarios, security_attack_suite), LLM, partners. |
| `policy/coordination_identity_policy.v0.1.yaml`, `policy/tool_boundary_policy.v0.1.yaml`, `policy/memory_policy.v0.1.yaml` | Coordination identity, tool boundary, memory policy (security controls). |
| `benchmarks/` | Baseline registry (baseline_registry.v0.1.yaml), official baselines (v0.1, v0.2). |
| `tests/` | Pytest: golden suite, policy validation, benchmarks, coordination, risk injections, studies, export, etc. |
| `tests/fixtures/` | Test data (coordination study smoke spec, legacy-injection spec, keys). |
| `examples/` | Example agents and scripts (external_agent_demo, scripted_ops_agent, llm_agent_mock_demo, etc.). |
| `scripts/` | Quickstart and paper-release scripts (shell, PowerShell). |
| `docs/` | MkDocs source (architecture, benchmarks, coordination, contracts, installation, STATUS, etc.). |
| `ui_fixtures/` | Minimal results, episode log, evidence bundle, FHIR for offline UI work. |
| `paper/` | Paper-related notes (README). |

## Source package (`src/labtrust_gym/`)

| Path | Purpose |
|------|---------|
| `config.py` | Repo root resolution for policy paths. |
| `engine/` | Core env, audit log, zones, specimens, QC, critical, queueing, devices, signatures, RBAC, transport, invariants, enforcement. |
| `coordination/` | Identity (Ed25519 key material, sign/verify), SignedMessageBus (replay protection, epoch binding). |
| `memory/` | Validators (poison/instruction-override detection), store (authenticated writes, TTL, filter on retrieval). |
| `tools/` | Registry, sandbox (egress/data-class limits), execution. |
| `envs/` | PettingZoo Parallel and AEC wrappers. |
| `baselines/` | Scripted ops/runner, adversary, insider, LLM (agent, backends, signing_proxy, parse_utils), coordination (interface, methods, registry, **adversary_coord**), MARL (PPO). |
| `benchmarks/` | Tasks (TaskA–TaskH), runner, metrics, coordination_scale, summarize, determinism_report, **security_runner**, **securitization**, **official_pack**. |
| `policy/` | Loader, validate, invariants_registry, coordination, risks, tokens, prompt_registry, reason_codes, emits. |
| `security/` | Risk injections, secret_scrubber, fs_safety, output_shaping, adversarial_detection, agent_capabilities, **safety_case**. |
| `studies/` | study_runner, coordination_study_runner, plots, reproduce, package_release. |
| `export/` | Receipts, FHIR R4, ui_export, verify (including optional policy fingerprints). |
| `online/` | HTTP server, authz, rate limit, telemetry. |
| `runner/` | Golden runner, adapter, emits validator. |
| `logging/` | Episode log. |
| `cli/` | Main CLI (validate-policy, run-benchmark, quick-eval, run-study, run-coordination-study, make-plots, etc.). |

## Where to put outputs

- **Benchmark results**: `labtrust run-benchmark ... --out labtrust_runs/bench/results.json` or use default `labtrust_runs/` for quick-eval.
- **Study outputs**: `labtrust run-study --out labtrust_runs/study_001` or `labtrust run-coordination-study --out labtrust_runs/coord_001`.
- **Plots**: `labtrust make-plots --run labtrust_runs/study_001` writes into that run’s `figures/` subdir.
- **Release artifact**: `labtrust package-release --out /tmp/labtrust_release` (outside repo). Paper profile (`--profile paper_v0.1`) also writes **SECURITY/** (attack_results.json, coverage, reason_codes, deps_inventory) and **SAFETY_CASE/** (safety_case.json, safety_case.md).
- **Security suite**: `labtrust run-security-suite --out <dir>` writes SECURITY/ under the given directory.
- **Safety case**: `labtrust safety-case --out <dir>` writes SAFETY_CASE/safety_case.json and safety_case.md under the given directory.
- **Official pack**: `labtrust run-official-pack --out <dir>` writes a single output tree (baselines/, SECURITY/, SAFETY_CASE/, transparency log, etc.) for the Official Benchmark Pack v0.1.

The directory `labtrust_runs/` is gitignored. Do not commit root-level `results.json`, `out.json`, `bench_smoke_*.json`, `ep.jsonl`, `quick_eval_*/`, or `ui_bundle.zip`; they are ignored so the root stays clean.
