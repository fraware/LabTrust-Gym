# Documentation mission checklist

This checklist tracks the comprehensive pass to ensure all files have appropriate comments, structure, and clear explanations (no jargon). Standards: [Documentation standards](documentation_standards.md).

## Completed

### Standards and reference

- **docs/reference/documentation_standards.md** — Created. Defines module/class/function docstrings, plain language, no unexplained jargon, structure.
- **CONTRIBUTING.md** — Added link to documentation standards.
- **mkdocs.yml** — Added "Documentation standards" under Reference.

### Package and engine

- **src/labtrust_gym/__init__.py** — Clearer package purpose and policy reference.
- **src/labtrust_gym/engine/__init__.py** — Describes package role and main exports.
- **src/labtrust_gym/engine/core_env.py** — Module docstring rewritten: explains golden scenarios, audit, tokens, zones, reception, QC, log_frozen.
- **src/labtrust_gym/engine/state.py** — Clearer InitialStateDict description.
- **src/labtrust_gym/engine/event.py** — Clearer StepEventDict and module docstring.
- **src/labtrust_gym/engine/audit_log.py** — Plain-language hash chain and fault injection.
- **src/labtrust_gym/engine/zones.py** — Zone graph and door rules explained without abbreviations.
- **src/labtrust_gym/engine/specimens.py** — Specimen lifecycle and reason codes.
- **src/labtrust_gym/engine/queueing.py** — Per-device queues and priority ordering.
- **src/labtrust_gym/engine/qc.py** — QC state and result gating in plain language.
- **src/labtrust_gym/engine/critical.py** — Critical result classification and notify/ack flow.
- **src/labtrust_gym/engine/devices.py** — Device state and run model.
- **src/labtrust_gym/engine/rbac.py** — RBAC spelled out and behavior described.
- **src/labtrust_gym/engine/signatures.py** — Action signature verification and key registry.
- **src/labtrust_gym/engine/transport.py** — Multi-site transport and invariants.
- **src/labtrust_gym/engine/invariants_runtime.py** — Invariant checks post-step.
- **src/labtrust_gym/engine/errors.py** — Engine reason codes and policy reference.

### Coordination

- **src/labtrust_gym/coordination/__init__.py** — Blackboard, views, bus described.
- **src/labtrust_gym/coordination/identity.py** — Signed identity and key derivation.
- **src/labtrust_gym/coordination/bus.py** — Replay-safe bus and epoch binding.
- **src/labtrust_gym/coordination/harness.py** — Blackboard and view replicas harness.
- **src/labtrust_gym/coordination/network.py** — Network simulator and determinism.

### CLI, policy, config, pipeline, viewer

- **src/labtrust_gym/cli/main.py** — CLI entry point and main commands.
- **src/labtrust_gym/policy/loader.py** — Policy load and validate.
- **src/labtrust_gym/config.py** — Repo and policy path resolution.
- **viewer/app.js** — Risk Register Viewer purpose and bundle schema reference.

## Completed (session 5)

### Viewer, scripts, examples

- **viewer/load_bundle.js** — Comment: loading sources including "Load latest release", schema ref.
- **scripts/refresh_sota_checklist.py** — SOTA spelled out (state of the art); run command.
- Scripts and examples already had clear docstrings/usage.

### Baselines

- **baselines/__init__.py** — Package docstring: scripted, adversary, LLM, MARL explained.
- **baselines/scripted_ops.py** — STAT/EDF and QC behavior in plain language.
- **baselines/adversary.py** — Module docstring: containment/detection purpose.
- **baselines/llm/agent.py** — LLM spelled out; backends and shield described.
- **baselines/coordination/registry.py** — Module docstring: policy load, extension point.

### Envs, runner, control_plane, online, memory (remaining)

- **envs/pz_aec.py** — AEC explained; sequential stepping, [env] extra.
- **runner/emits_validator.py** — Module docstring: vocab validation for golden runner.
- **control_plane/gates.py** — RBAC, capability, signature; removed B006.
- **online/config.py** — Auth modes in plain language; removed B007 from docstring.
- **memory/validators.py** — Already clear.

### Studies

- **studies/package_release.py** — Module docstring: release artifact, profiles.
- **studies/coordination_summarizer.py** — SOTA spelled out; leaderboard and method-class.

## Completed (session 4)

### Benchmarks and studies

- **benchmarks/__init__.py** — Package docstring: tasks, metrics, runner, official pack.
- **benchmarks/tasks.py** — Module docstring: task definitions, determinism.
- **benchmarks/metrics.py** — Module docstring: per-episode metrics, constants.
- **benchmarks/summarize.py** — Module docstring: aggregate results, CSV/md output.
- **benchmarks/official_pack.py** — Module docstring: pack policy, baselines, v0.2.
- **benchmarks/baseline_registry.py** — Module docstring: task -> baseline_id.
- **benchmarks/determinism_report.py** — Module docstring: run twice, compare hashes, CI gate.
- **benchmarks/security_runner.py** — Module docstring: attack suite, LLM spelled out.
- **studies/__init__.py** — Package docstring: run_study, coordination studies.
- **studies/study_runner.py** — Module docstring: Cartesian conditions, artifact layout.
- **studies/coordination_study_runner.py** — Module docstring: scale x method x injection, LLM.

### Envs, runner, orchestrator, online, memory, control_plane, domain

- **envs/__init__.py** — Package docstring: Parallel and AEC wrappers, [env] extra.
- **envs/pz_parallel.py** — Module docstring: PettingZoo Parallel, observations, actions.
- **runner/__init__.py** — Package docstring: GoldenRunner, adapter, emits validation.
- **runner/golden_runner.py** — Module docstring: scenario suite, contract, emits.
- **orchestrator/__init__.py** — Package docstring: live orchestration, defense, config.
- **online/__init__.py** — Package docstring: HTTP API, rate limits, auth (B004 removed).
- **online/server.py** — Module docstring: serve command, /v0/step, telemetry.
- **memory/__init__.py** — Package docstring: store, validators, TTL explained.
- **memory/store.py** — Module docstring: put/get, auth, schema, poison filter.
- **control_plane/__init__.py** — Package docstring: gates, enforcement.
- **control_plane/interface.py** — Module docstring: ControlPlane protocol, GateDecision.
- **domain/__init__.py** — Package docstring: pluggable domains, forkers.

## Completed (session 3)

### Policy, security, export, tools, auth, logging

- **policy/validate.py** — Module docstring: CLI validation, runner contract, schemas, partner overlay.
- **policy/coordination.py** — Module docstring: method registry, matrix, study spec; LLM spelled out.
- **policy/gate_eval.py** — Module docstring: gate = pass/fail threshold, verdicts, rule types, metrics source.
- **policy/invariants_registry.py** — Module docstring: invariants = safety rules; InvariantEntry severity/scope.
- **security/__init__.py** — Package docstring: detection, capabilities, secrets, path safety, risk injection.
- **security/risk_injections.py** — Module docstring: coordination-risk benchmark, deterministic, auditable.
- **export/__init__.py** — Package docstring: receipts, evidence, FHIR, verification, UI export.
- **export/receipts.py** — Module docstring: receipt = per-specimen/result audit record; bundle contents.
- **tools/__init__.py** — Package docstring: registry, validation, capability gating, sandbox, engine use.
- **auth/__init__.py** — Package docstring: authorization for tools, RBAC, evidence fingerprint.
- **auth/authorize.py** — Module docstring: is_tool_allowed, rbac_policy_fingerprint, RBAC explained.
- **logging/__init__.py** — Package docstring: episode JSONL, step timing, determinism.

## Completed (session 2)

### Engine (remaining)

- **engine/catalogue_runtime.py** — Module docstring: catalogue, stability, reagent gating in plain language.
- **engine/enforcement.py** — Module docstring: violations, enforcement map, escalation, audit; EnforcementItem comment.
- **engine/policy_resolution.py** — Module docstring: effective_policy vs file vs default.
- **engine/tokens_runtime.py** — Module docstring: token lifecycle, replay protection, engine use.
- **engine/model_checking.py** — Module docstring: invariants, trace format, output files.
- **engine/rng.py** — MTTR expanded to "mean time to repair" in sample_lognormal_s.

## Remaining (by area)

Use the same standards: module docstring (what and where it fits), no unexplained jargon, clear class/function docstrings where public or non-obvious.

### Engine

- engine/clock.py — Already clear; optional light polish only.

### Baselines

- baselines/llm/* (other modules), baselines/marl/*, baselines/coordination/methods/* — Module docstrings where missing; explain acronyms in new text.

### Benchmarks and studies

- benchmarks/coordination_scale.py, result_builder.py, pareto.py, llm_trace.py, securitization.py — Optional polish.
- studies/*.py (matrix_view, coordination_card, package_release, plots, etc.) — Module docstrings where missing.

### Policy, security, export, tools, auth, etc.

- Other policy modules (e.g. tokens, risks, loader already done) — module docstrings where missing.
- Other security/*.py, export/*.py, tools/*.py (e.g. verify.py, fhir_r4.py, sandbox.py) — module docstrings.

### Envs, runner, orchestrator, online, memory, control_plane, domain

- envs/pz_aec.py, runner/emits_validator.py, control_plane/gates.py, online/config.py — Done (session 5).
- runner/adapters/*.py, orchestrator/replay.py, shadow.py, online/rate_limit.py, telemetry.py, authz.py — Module docstrings where missing.

### Tests

- tests/*.py — At least a one-line module docstring per file; comment non-obvious assertions or contract assumptions.

### Scripts and examples

- scripts/*.py — Docstrings already present; refresh_sota_checklist SOTA explained (session 5).
- examples/*.py, examples/*.ipynb — Already have clear purpose and usage.

### Viewer and docs

- viewer/load_bundle.js — Done (session 5).
- docs/*.md — Ensure overview paragraphs and no outdated paths; align with repository_structure.md.

## How to continue

1. Pick an area from "Remaining" and open its files.
2. For each file: add or refine the module docstring; add class/function docstrings for public or complex pieces; replace jargon with a short explanation or link.
3. Mark the file in this checklist under a "Completed (session 2)" (or similar) section.
4. Run `ruff check` and `mypy src/` after edits; fix any new issues.

This mission is incremental: complete one area at a time and update this checklist so the next session can resume easily.
