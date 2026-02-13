# LabTrust-Gym — Current State of the Repo

This document reports what is implemented, what is not, and what remains to reach the north star (pip-installable multi-agent lab environment with trust skeleton, benchmarks, and baselines).

## Summary (3-min)

- **North star:** Pip-installable multi-agent lab environment (PettingZoo/Gym style) with trust skeleton (RBAC, signed actions, hash-chained audit log, invariants, reason codes) and benchmarks (tasks and baselines with safety/throughput trade-offs).
- **Release:** v0.1.0 contract freeze. Frozen contracts: runner output, queue, invariant registry, enforcement, receipt, evidence bundle, FHIR, results v0.2/v0.3. See [Frozen contracts](frozen_contracts.md).
- **Trust skeleton:** Policy validation, audit/hashchain, RBAC, signatures/key registry, tokens, zones, specimens, QC, critical results, catalogue, stability, queueing, transport, invariant registry and enforcement, runtime control (shift-change). Golden suite: 34 scenarios.
- **Benchmarks and artifacts:** Tasks throughput_sla through coord_risk; scripted, adversary, insider, LLM, MARL, coordination baselines. Official pack v0.1/v0.2, paper_v0.1 profile, security suite (prompt-injection defense: pre-LLM block, output consistency), safety case. Export: receipts, FHIR (valid R4: data-absent-reason for missing specimen/value; no placeholder IDs), verify-bundle, ui-export. Risk register: evidence gaps (status=missing) first-class; **validate-coverage --strict** fails if required risks have missing evidence.
- **CLI:** validate-policy, quick-eval, run-benchmark, export-receipts, export-fhir, verify-bundle, **validate-coverage**, run-security-suite, safety-case, run-official-pack, package-release, reproduce, etc. See [index](index.md).

**Last updated:** reflects the codebase after **SOTA coordination methods** (consensus_paxos_lite, swarm_stigmergy_priority in registry and policy; coordination-nightly SOTA sanity runs four methods including these), **risk-coverage-strict** CI job (schedule/workflow_dispatch: validate-coverage --strict; see [CI](ci.md)), **paper provenance** (docs/paper/README.md: seeds column, PAPER_CLAIMS alignment, paper-ready artifact command), **engine state/event** (state.py InitialStateDict, event.py StepEventDict used by core_env reset/step), **LLM standards-of-excellence** (docs/llm_live.md: LLM coordination entry points and checklist table), **prompt-injection defense** (policy/security/prompt_injection_defense.v0.1.yaml; pre-LLM block, optional sanitization, output consistency; expanded adversarial_detection patterns and prompt_injection_scenarios; integration in LLMAgentWithShield; tests test_prompt_injection_defense.py, golden test delta excludes pre-LLM blocks), **PPO/MARL enhancements** (train_config: net_arch, learning_rate, n_steps, obs_history_len, reward_scale_schedule; train_config.json written at training start and used by eval/PPOAgent; eval-ppo and _eval_policy auto-load train_config.json; PPOAgent loads device_ids and obs_history_len from train_config.json; run_ppo_optuna with optional marl_hpo extra; tests test_ppo_wrapper.py, test_marl_smoke_ppo_train_config_and_history), **PPO reward design** (throughput_sla `schedule_reward` for accepted QUEUE_RUN; PPOAgent for `eval-agent` with `LABTRUST_PPO_MODEL`), **datetime.utcnow** deprecation fix (CLI uses `datetime.now(UTC)`), **LabTrustParallelEnv.render_mode** (optional constructor arg to satisfy PettingZoo conversion), **full test suite** (pytest -v: 1100+ tests; many skipped without env vars: MARL smoke, golden, llm_live), **coordination-nightly** (`.github/workflows/coordination-nightly.yml`: schedule + workflow_dispatch; coordination-security-pack, coordination-study smoke, minimal SOTA sanity), **summarize-coordination** (`labtrust summarize-coordination --in <dir> --out <dir>`; SOTA leaderboard + method-class comparison from summary_coord.csv; study runner writes summary/sota_leaderboard.csv, sota_leaderboard.md, method_class_comparison.csv, method_class_comparison.md; summary CSV includes **coordination.stale_action_rate**), **benchmarking plan** (`docs/benchmarking_plan.md`; three-layer matrix: Layer 1 sanity, Layer 2 coverage, Layer 3 scale; scripts run_benchmarking_layer1_sanity, run_benchmarking_layer2_coverage, run_benchmarking_layer3_scale), **SOTA fidelity checklist** (see [Coordination methods](coordination_methods.md) SOTA fidelity checklist section); algorithmic and evaluation fidelity for coordination methods), **e2e-artifacts-chain** (scripts/ci_e2e_artifacts_chain.sh, make e2e-artifacts-chain, e2e-artifacts-chain.yml), **llm_live optional smoke** (llm_live_optional_smoke.yml; healthcheck + pack smoke when OPENAI_API_KEY set), **anthropic_live** backend and **run-cross-provider-pack** (openai_live, anthropic_live, ollama_live; summary_cross_provider.json/.md), **Official Benchmark Pack v0.2** (live coordination evaluation protocol: required metadata, cost accounting, reproducibility expectations; `policy/official/benchmark_pack.v0.2.yaml`; when `--pipeline-mode llm_live`, pack runner writes `TRANSPARENCY_LOG/llm_live.json` and `live_evaluation_metadata.json`; validator and risk-register exporter accept these artifacts; risk register links include them when present), **risk register contract gate** (CI job **risk-register-gate**: generate bundle from ui_fixtures, validate schema, run contract gate tests — schema, snapshot, crosswalk integrity, coverage gate; `check_crosswalk_integrity`, `check_risk_register_coverage` in export/risk_register_bundle.py; snapshot `tests/fixtures/risk_register_bundle_ui_fixtures.v0.1.json`; **docs/risk_register.md** for bundle overview, generation from fixtures/paper/official pack, review workflow; **scripts/run_external_reviewer_risk_register_checks.sh** and **.ps1** for external reviewer: security/coord smoke or provided dirs, export-risk-register, schema + crosswalk validation, optional verify-bundle), **coordination security pack** (`labtrust run-coordination-security-pack`; fixed scale × method × injection matrix, pack_results/, pack_summary.csv, pack_gate.md; policy-driven gate thresholds; see security_attack_suite.md), **LLM fault model** (llm_offline deterministic fault injection: invalid_output, empty_output, high_latency, inconsistent_plan; policy/llm/llm_fault_model.v0.1.yaml; fault_injected_rate, fallback_rate metrics; see llm_live.md), **LLM coordination improvements** (repair loop with shield-only execute and runner integration; shield outcome hash from step_results in single-shot path; coverage gate in external reviewer script; INJ-BID-SPOOF-001 doc/comment; ollama_live for llm_central_planner, llm_hierarchical_allocator, llm_auction_bidder; .gitattributes for `*.sh` LF), **safety case generator**, **coordination red team** (injections v0.2, adversary strategies, stealth/attribution/blast-radius metrics), **Official Benchmark Pack v0.1**, and the above. **Safety case:** `policy/safety_case/claims.v0.1.yaml`; `src/labtrust_gym/security/safety_case.py` (build_safety_case, emit_safety_case → SAFETY_CASE/safety_case.json, safety_case.md); CLI `labtrust safety-case --out <dir>`; integrated into package-release paper_v0.1 and run-official-pack; tests test_safety_case_generation.py. **Red team:** `policy/coordination/injections.v0.2.yaml` (success_definition, detection_definition, containment_definition); `baselines/adversary_coord.py` (adversarial strategies); metrics sec.stealth_success_rate, sec.time_to_attribution_steps, sec.blast_radius_proxy; tests test_coord_red_team_definitions.py. **Official pack:** `policy/official/benchmark_pack.v0.1.yaml` (default), `benchmark_pack.v0.2.yaml` (when `--pipeline-mode llm_live`); `benchmarks/official_pack.py` (run_official_pack, load_benchmark_pack with prefer_v02); CLI `labtrust run-official-pack --out <dir> [--pipeline-mode llm_live] [--allow-network]`; llm_live runs write TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json; tests test_official_pack_smoke.py. **Security attack suite:** `policy/golden/security_attack_suite.v0.1.yaml`; security_runner, securitization; package-release paper_v0.1; CLI run-security-suite. **Verify-bundle:** optional coordination_policy_fingerprint, memory_policy_fingerprint. **Coordination identity:** identity.py, bus.py; coordination_identity_policy.v0.1.yaml; COORD_* reason codes. **Tool sandbox:** tools/sandbox.py; tool_boundary_policy.v0.1.yaml. **Memory hardening:** memory/validators.py, store.py; memory_policy.v0.1.yaml. Earlier: coordination-at-scale (coord_scale/coord_risk, COORDINATION_CARD), B008/B009, LLM extensions, ui-export, key registry lifecycle, insider_key_misuse, invariant registry v1.0, transport, export, package-release, quick-eval, PyPI packaging, GS-SHIFT-CHANGE-001.

---

## 1. Repo layout vs design

### 1.1 Implemented and aligned with design

| Area | Status | Notes |
|------|--------|--------|
| **Root metadata** | ✅ | README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, LICENSE (Apache-2.0), .gitignore. Root kept minimal: CLI/build artifacts (results*.json, out.json, bench_smoke_*.json, quick_eval_*/, site/) ignored; use `labtrust_runs/` or `--out` for outputs. **docs/repository_structure.md** documents layout. |
| **CI** | ✅ | `.github/workflows/ci.yml`, `release.yml`; ruff format/check, mypy, pytest, policy validation; **risk-register-gate** (generate bundle from tests/fixtures/ui_fixtures, schema + contract gate tests); **risk-coverage-strict** (schedule/workflow_dispatch: validate-coverage --strict; see [CI](ci.md)); optional bench-smoke and **coordination-smoke** (nightly/manual); **e2e-artifacts-chain.yml** (package-release → verify-bundle → export-risk-register); **llm_live_optional_smoke.yml** (healthcheck + pack smoke when OPENAI_API_KEY set); **coordination-nightly.yml** (schedule + workflow_dispatch: coordination-security-pack, coordination-study smoke, SOTA sanity for kernel_whca, ripple_effect, consensus_paxos_lite, swarm_stigmergy_priority; Layer 3 corridor_heavy 1 ep; see [CI](ci.md)). |
| **Policy tree** | ✅ | `policy/schemas/` (includes **llm_fault_model.v0.1.schema.json**), `policy/emits/`, `policy/invariants/`, `policy/tokens/`, `policy/reason_codes/`, `policy/zones/`, `policy/keys/`, `policy/rbac/`, `policy/catalogue/`, `policy/stability/`, `policy/equipment/`, `policy/critical/`, **`policy/risks/`** (risk_registry.v0.1), **`policy/coordination/`** (coordination_methods.v0.1, method_risk_matrix.v0.1, coordination_study_spec.v0.1, scale_configs.v0.1, resilience_scoring.v0.1, **injections.v0.2**, **coordination_security_pack_gate.v0.1**), **`policy/safety_case/`** (claims.v0.1.yaml), **`policy/official/`** (benchmark_pack.v0.1.yaml, benchmark_pack.v0.2.yaml for llm_live), **`policy/coordination_identity_policy.v0.1.yaml`**, **`policy/tool_boundary_policy.v0.1.yaml`**, **`policy/memory_policy.v0.1.yaml`**, **`policy/llm/`** (**llm_fault_model.v0.1.yaml**, defaults, prompt_registry), `policy/golden/` (golden_scenarios, prompt_injection_scenarios, **security_attack_suite.v0.1**), `policy/partners/`, `policy/sites/`, `policy/studies/`. |
| **Source tree** | ✅ | `src/labtrust_gym/`: config, engine/, **coordination/** (identity, bus), **memory/** (validators, store), **tools/** (registry, sandbox, execution), policy/ (loader, validate, invariants_registry, risks, coordination, prompt_registry), **security/** (secret_scrubber, fs_safety, output_shaping, risk_injections, adversarial_detection, agent_capabilities, **safety_case**), runner/, export/, envs/, **baselines/** (scripted, adversary, **llm** (agent, backends, **fault_model**), coordination: interface, methods, registry, **adversary_coord**; marl), **benchmarks/** (tasks throughput_sla through coord_risk, runner, coordination_scale, metrics, summarize, **security_runner**, **securitization**, **official_pack**), **studies/** (study_runner, coordination_study_runner, **coordination_security_pack**, plots, reproduce, package_release), logging/, online/, cli/. |
| **Tests** | ✅ | Golden suite, policy validation, hashchain, tokens, zones, specimens, qc, critical, queueing, benchmarks, enforcement, study_runner, **coordination** (scale, methods, study, policy, **test_coordination_security_pack**; **test_coordination_identity_bus**, **test_coord_red_team_definitions**), **risk_injections**, **test_llm_fault_model**, **test_tool_sandbox**, **test_memory_hardening**, **test_security_attack_suite**, **test_securitization**, **test_safety_case_generation**, **test_official_pack_smoke**, export, **test_risk_register_bundle**, **test_risk_register_contract_gate** (schema, snapshot, crosswalk, coverage gate), online, etc. |
| **Examples** | ✅ | `examples/`: minimal_random_policy_agent, scripted_ops_agent, scripted_runner_agent, llm_agent_mock_demo, external_agent_demo. |
| **Docs** | ✅ | **`repository_structure.md`** (directory layout, where to put outputs), `architecture.md`, `installation.md`, `policy_pack.md`, `threat_model.md`, `invariants_registry.md`, `enforcement.md`, `benchmarks.md`, `benchmark_card.md` (coord_scale/coord_risk, coordination suite), **`benchmarking_plan.md`** (three-layer matrix), `studies.md`, **coordination** (`coordination_methods.md`, `coordination_scale.md`, `coordination_studies.md`, `coordination_policy.md`, `coordination_benchmark_card.md`; checklists in coordination_methods), **`official_benchmark_pack.md`**, **`implementation_verification.md`** (safety case, controls, artifacts), `reproduce.md`, `fhir_export.md`, `frozen_contracts.md`, `ui_data_contract.md`, **`risk_register.md`**, **`risk_register_contract.v0.1.md`**, **`risk_register_viewer.md`**, `deployment_hardening.md`, `output_controls.md`, `security_online.md`, `online_mode.md`, `ci.md`, `pettingzoo_api.md`, `queue_contract.v0.1.md`, `marl_baselines.md`, `llm_baselines.md`, **`llm_live.md`**, **`security_attack_suite.md`** (includes **coordination security pack**), `STATUS.md`, **systems_and_threat_model.md**, **example_experiments.md**, **build_your_own_agent.md**, **PAPER_CLAIMS.md**. **ui_fixtures/** for offline UI. MkDocs site; **CITATION.cff** at repo root. |

### 1.2 Not present or partial (from original directory spec)

- **Engine:** `state.py`, `event.py`, `errors.py` — no dedicated modules; state is dict-based in core_env and sub-stores. `clock.py`, `rng.py`, `devices.py`, `queueing.py` exist.
- **Policy schemas:** All policy YAML/JSON listed in `POLICY_FILES_WITH_SCHEMAS` have JSON schemas under `policy/schemas/` and are validated by `labtrust validate-policy`. Invariant registry (v1.0) and enforcement map (v0.1) are included and validated.

### 1.3 What's frozen (anti-regression backbone)

Contracts and schema versions that define correctness; do not weaken without explicit design change and version bump. See **[Frozen contracts](frozen_contracts.md)** for the canonical list:

- **Runner output contract** — `policy/schemas/runner_output_contract.v0.1.schema.json` (step return shape: status, emits, violations, hashchain, etc.).
- **Queue contract** — `docs/queue_contract.v0.1.md` (device queue semantics, QUEUE_RUN / START_RUN, queue_head).
- **Invariant registry schema** — `policy/schemas/invariant_registry.v1.0.schema.json`.
- **Enforcement map schema** — `policy/schemas/enforcement_map.v0.1.schema.json`.
- **Study spec schema** — `policy/studies/study_spec.schema.v0.1.json`.
- **Receipt schema** — `policy/schemas/receipt.v0.1.schema.json` (per-specimen/result receipt for evidence bundle).
- **Evidence bundle manifest schema** — `policy/schemas/evidence_bundle_manifest.v0.1.schema.json`.
- **FHIR bundle export schema** — `policy/schemas/fhir_bundle_export.v0.1.schema.json`.
- **Sites policy schema** — `policy/schemas/sites_policy.v0.1.schema.json` (multi-site topology, routes, transport_time, temp_drift).
- **Key registry schema** — `policy/schemas/key_registry.v0.1.schema.json` (Ed25519 keys; optional status ACTIVE/REVOKED/EXPIRED, not_before_ts_s/not_after_ts_s; lifecycle enforced in signature verification).
- **RBAC policy schema** — `policy/schemas/rbac_policy.v0.1.schema.json` (roles, agents, action_constraints).

---

## 2. What was implemented

### 2.1 Policy loading and validation

- **`src/labtrust_gym/policy/loader.py`** — Loads YAML/JSON from policy paths; validates against JSON Schema via `validate_against_schema`; `POLICY_FILE_SCHEMA_MAP` maps policy filenames to schema filenames.
- **`src/labtrust_gym/policy/validate.py`** — Used by CLI; validates runner output contract schema file (exists and valid JSON); validates all policy files in `POLICY_FILES_WITH_SCHEMAS` against their JSON schemas (emits vocab, zones, reason codes, token registry, dual approval, critical thresholds, equipment registry, golden scenarios).
- **Policy schemas** — `policy/schemas/` contains JSON schemas for: emits_vocab.v0.1, zone_layout_policy.v0.1, reason_code_registry.v0.1, token_registry.v0.1, dual_approval_policy.v0.1, critical_thresholds.v0.1, equipment_registry.v0.1, golden_scenarios.v0.1, plus runner_output_contract.v0.1 and test_catalogue.schema.v0.1.
- **CLI** — `labtrust validate-policy` runs full policy validation (all policy files against schemas). `labtrust validate-policy --partner <partner_id>` also validates overlay files and merged policy consistency.
- **Partner overlays** — `policy/partners/partners_index.v0.1.yaml`; per-partner dirs (e.g. `hsl_like/`) with overrides for critical, stability, enforcement, equipment. Loader: `load_effective_policy(root, partner_id)` returns merged policy and `policy_fingerprint`. Merge rules per type in `policy/overlay.py`. Engine uses `initial_state["effective_policy"]` when present.
- **Tests** — `tests/test_policy_validation.py`, `tests/test_partner_overlay.py` (overlay load/merge determinism, invalid overlay fails schema, benchmark smoke with partner).

### 2.2 Golden runner and harness

- **`src/labtrust_gym/runner/adapter.py`** — `LabTrustEnvAdapter` interface (reset, step, query).
- **`src/labtrust_gym/runner/golden_runner.py`** — Scenario execution, assertions (status, emits, violations, blocked_reason_code, token_consumed, state_assertions, hashchain), output matches runner contract shape.
- **`src/labtrust_gym/runner/emits_validator.py`** — `load_emits_vocab(path)`, `validate_emits(emits, allowed, event_id)`; GoldenRunner enforces emits vocab (unknown emits ⇒ AssertionError).
- **`tests/test_golden_suite.py`** — Loads runner output contract schema, validates step output via jsonschema; fails if any scenario failed; gated by `LABTRUST_RUN_GOLDEN=1`; uses fallback adapter when env var unset (tests skipped).

### 2.3 Audit hashchain and forensic freeze

- **`src/labtrust_gym/engine/audit_log.py`** — Canonical event serialization (deterministic), SHA-256 hash chain, append(event) → head_hash, last_event_hash, length; fault injection `break_hash_prev_on_event_id`; chain break → forensic freeze.
- **`src/labtrust_gym/engine/core_env.py`** — Minimal engine: reset(initial_state, deterministic, rng_seed), step(event) returns contract (status, emits, violations, blocked_reason_code, token_consumed, hashchain); once log_frozen, all steps BLOCKED with AUDIT_CHAIN_BROKEN; FORENSIC_FREEZE_LOG emitted at freeze.
- **query(expr)** — `system_state('log_frozen')`, `last_reason_code_system`.
- **Tests** — `tests/test_hashchain.py` (unit + integration); GS-022 passes when `LABTRUST_RUN_GOLDEN=1` with real engine.

### 2.4 Emits and reason codes (strict validation)

- **`policy/emits/emits_vocab.v0.1.yaml`** — Canonical set of allowed emit types.
- **`src/labtrust_gym/policy/emits.py`** — Load vocab, validate engine step emits.
- **`policy/reason_codes/reason_code_registry.v0.1.yaml`** — Starter registry (AUDIT_CHAIN_BROKEN, AUDIT_MISSING_REASON_CODE, RC_DEVICE_NOT_COLOCATED, ID_MISMATCH, CNT_CITRATE_FILL_INVALID, INT_LEAKING, QC_FAIL_ACTIVE, CRIT_NO_ACK, TIME_EXPIRED, TEMP_OUT_OF_BAND, RBAC_RESTRICTED_ENTRY_DENY, etc.).
- **`src/labtrust_gym/policy/reason_codes.py`** — Load registry, validate code exists, lookup.
- **GoldenRunner** — When `LABTRUST_STRICT_REASON_CODES=1`, blocked_reason_code and action reason_code must be in registry.
- **Tests** — `tests/test_emits_and_reason_codes.py` (strict and non-strict modes).

### 2.5 Token lifecycle and dual approval

- **`src/labtrust_gym/policy/tokens.py`** — Token dataclass, dual-approval validation (two distinct approvers/keys), lifecycle (ACTIVE → CONSUMED/REVOKED/EXPIRED).
- **`src/labtrust_gym/engine/tokens_runtime.py`** — Token store: mint_token, consume_token, revoke_token, is_valid(token_id, t_s); replay protection (consumed/expired/revoked invalid).
- **Engine** — MINT_TOKEN, REVOKE_TOKEN; any action with token_refs validated; consumed on use.
- **Tests** — `tests/test_tokens.py`; GS-010–GS-013 pass under `LABTRUST_RUN_GOLDEN=1`.

### 2.5.5 RBAC policy (action permissions + role bindings)
- **`policy/rbac/rbac_policy.v0.1.yaml`** — roles (allowed_actions, allowed_zones, allowed_devices), agents (agent_id → role_id), optional action_constraints.
- **`src/labtrust_gym/engine/rbac.py`** — load_rbac_policy(path), check(agent_id, action_type, context, policy) → (allowed, reason_code, rbac_decision); get_agent_role(agent_id, policy).
- **Engine** — RBAC gate is the **first** gate in step (before tokens, before domain logic); BLOCKED with RBAC_ACTION_DENY / RBAC_ZONE_DENY / RBAC_DEVICE_DENY; rbac_decision recorded in step output (receipts/forensics). INV-SIG-002: when action is signed, key's role must match RBAC role for agent_id.
- **Reason codes** — RBAC_ACTION_DENY, RBAC_ZONE_DENY, RBAC_DEVICE_DENY.
- **Tests** — `tests/test_rbac.py`; GS-RBAC-028 (unauthorized RELEASE_RESULT blocked), GS-RBAC-029 (token cannot bypass RBAC).

### 2.5.6 Signatures and key registry (lifecycle)
- **`policy/keys/key_registry.v0.1.yaml`** — Ed25519 public keys: key_id, public_key (base64), agent_id, role_id; optional **status** (ACTIVE, REVOKED, EXPIRED; default ACTIVE), **not_before_ts_s** / **not_after_ts_s** (validity window). Schema: `policy/schemas/key_registry.v0.1.schema.json` (all lifecycle fields optional for backward compatibility).
- **`src/labtrust_gym/engine/signatures.py`** — load_key_registry(path), verify_action_signature(event, prev_hash, partner_id, policy_fingerprint, registry, now_ts). Verification checks: key exists; status ACTIVE (or omitted); now_ts in [not_before_ts_s, not_after_ts_s]; key bound to event agent_id; INV-SIG-002 role match; Ed25519 signature over canonical payload. Reason codes: SIG_MISSING, SIG_INVALID, **SIG_KEY_REVOKED**, **SIG_KEY_EXPIRED**, **SIG_KEY_NOT_YET_VALID**, SIG_ROLE_MISMATCH.
- **Engine** — When strict_signatures and mutating action: missing/invalid/revoked/expired signature → BLOCKED with above reason codes. insider_key_misuse runs with strict_signatures True; insider phase 4 uses revoked key_id → BLOCKED SIG_KEY_REVOKED.
- **Tests** — `tests/test_signatures_key_lifecycle.py` (valid key passes; revoked/expired/not-yet-valid blocked; missing status defaults ACTIVE).

### 2.6 Zone graph and doors

- **`policy/zones/zone_layout_policy.v0.1.yaml`** — Zones, graph_edges, doors (including D_RESTRICTED_AIRLOCK), device_placement (device_id → zone_id).
- **`src/labtrust_gym/engine/zones.py`** — ZoneState: adjacency, agent positions, door open_since, tick() for door-open-too-long → ALARM, KILL_SWITCH_ZONE, zone frozen; move(), open_door(); build_device_zone_map(device_placement), get_default_device_zone_map().
- **Engine** — MOVE (adjacency; restricted zone requires token); OPEN_DOOR (restricted requires TOKEN_RESTRICTED_ENTRY); TICK door breach.
- **query(expr)** — `zone_state('Z_RESTRICTED_BIOHAZARD')` → 'frozen' | 'normal'.
- **Tests** — `tests/test_zones.py`; GS-008, GS-009, GS-020 pass.

### 2.7 Reception / specimen acceptance

- **`src/labtrust_gym/engine/specimens.py`** — SpecimenStore: state machine, templates (S_BIOCHEM_OK, S_COAG_OK); CREATE_ACCESSION, CHECK_ACCEPTANCE_RULES, ACCEPT_SPECIMEN, REJECT_SPECIMEN, HOLD_SPECIMEN; ID mismatch → reject (ID_MISMATCH); leaking → reject (INT_LEAKING); citrate underfill → hold (CNT_CITRATE_FILL_INVALID); HOLD_SPECIMEN without reason_code → BLOCKED AUDIT_MISSING_REASON_CODE.
- **Engine** — All acceptance actions wired; BLOCKED does not mutate specimen state.
- **Tests** — `tests/test_specimens.py`; GS-003, GS-004, GS-005, GS-021 pass.

### 2.8 QC and result gating

- **`src/labtrust_gym/engine/qc.py`** — QCStore: device qc_state, run–device mapping, results (status, flags); QC_EVENT, RERUN_REQUEST, START_RUN, GENERATE_RESULT, RELEASE_RESULT, HOLD_RESULT, RELEASE_RESULT_OVERRIDE (TOKEN_QC_DRIFT_OVERRIDE, QC_DRIFT_DISCLAIMER_REQUIRED).
- **Engine** — If device qc_state == fail, RELEASE_RESULT BLOCKED (QC_FAIL_ACTIVE); after QC pass, release allowed; drift override path with token and flag.
- **query(expr)** — `result_status('...')`, `result_flags('...')`.
- **Tests** — `tests/test_qc.py`; GS-014, GS-015 pass.

### 2.9 Critical results

- **`policy/critical/critical_thresholds.v0.1.yaml`** — Demo thresholds (non-clinical; K, Na, Hb, INR, etc.).
- **`policy/critical/escalation_ladder.v0.2.yaml`** — Tiers (primary_contact → secondary → consultant_registrar → duty_manager), allowed_contact_modes, max_ack_wait_s, required_fields, requires_readback; minimum_record_fields for comm records.
- **`src/labtrust_gym/engine/critical.py`** — Classify CRIT_A/CRIT_B/none; CriticalStore (v0.2): attempt records (attempt_id, tier), comm records; NOTIFY_CRITICAL_RESULT (creates attempt, validates mode); ACK_CRITICAL_RESULT (requires attempt_id, required_fields, readback when required); ESCALATE_CRITICAL_RESULT (tier order enforced); can_escalate(result_id, now_s) after max_ack_wait_s; RELEASE_RESULT blocked until compliant ACK.
- **Engine** — RELEASE_RESULT blocked until ACK recorded for critical results; downtime_active → auto NOTIFY_CRITICAL_RESULT on generate, phone/bleep path. Reason codes: CRIT_ACK_MISSING_FIELDS, CRIT_ESCALATION_OUT_OF_ORDER, CRIT_ACK_TIMEOUT, CRIT_MODE_NOT_ALLOWED.
- **query(expr)** — `result_criticality('...')`, `comm_record_exists(result_id='...')`, `notification_mode_required('...')`.
- **Tests** — `tests/test_critical.py`; GS-016, GS-017, GS-018, GS-CRIT-023, GS-CRIT-024, GS-CRIT-025 pass (when LABTRUST_RUN_GOLDEN=1).

### 2.10 Catalogue and stability (START_RUN gating)

- **`policy/catalogue/test_catalogue.seed.v0.1.json`**, **`policy/schemas/test_catalogue.schema.v0.1.json`** — Catalogue seed and schema.
- **`policy/stability/stability_policy.v0.1.yaml`** — Panel-level windows (biochem ambient pre-spin, coag, etc.).
- **`src/labtrust_gym/engine/catalogue_runtime.py`** — Panel lookup by specimen.panel_id, check_stability(), check_temp_out_of_band(); default_stability_limits.
- **Engine** — START_RUN: stability and temp checks; TIME_EXPIRED / TEMP_OUT_OF_BAND BLOCKED unless OVERRIDE_RISK_ACCEPTANCE; START_RUN_OVERRIDE with dual-approval token; CENTRIFUGE_END (separated_ts_s), ALIQUOT_CREATE (aliquot→specimen mapping).
- **Tests** — `tests/test_stability.py`, `tests/test_catalogue.py`; GS-001, GS-006, GS-007 pass.

### 2.11 Co-location (device–agent zone)

- **Device–zone mapping** — From `policy/zones/zone_layout_policy.v0.1.yaml` `device_placement` (and default in zones.py).
- **Engine** — START_RUN and START_RUN_OVERRIDE: if agent zone ≠ device zone ⇒ BLOCKED RC_DEVICE_NOT_COLOCATED, INV-ZONE-002:VIOLATION.
- **Tests** — `tests/test_zones.py` (build_device_zone_map, GS-019, unit colocation test); GS-019 passes.

### 2.12 Queueing (QUEUE_RUN, queue_head, START_RUN consume)

- **Contract (frozen):** **`docs/queue_contract.v0.1.md`** — Device queue item fields, priority ordering rule (STAT/URGENT/ROUTINE), QUEUE_RUN and START_RUN interaction, meaning of `queue_head()`. Do not weaken; queue semantics are a core knob for fairness vs. latency vs. safety.
- **`src/labtrust_gym/engine/queueing.py`** — DeviceQueueItem, DeviceQueue, QueueStore; ordering: priority_rank → enqueued_ts_s → tie_break; enqueue, queue_head(device_id), consume_head(device_id).
- **Engine** — QUEUE_RUN: device_id + work_id (or specimen_id/accession_ids/aliquot_ids); co-location; emit QUEUE_RUN. START_RUN: no explicit work ⇒ consume queue head (else RC_QUEUE_EMPTY); explicit work ⇒ strict work_id == queue_head then consume. Reason codes: RC_DEVICE_UNKNOWN, RC_QUEUE_BAD_PAYLOAD, RC_QUEUE_DUPLICATE_WORK_ID, RC_QUEUE_EMPTY, RC_QUEUE_HEAD_MISMATCH.
- **query(expr)** — `queue_head(DEVICE_ID)` → work_id at front or None.
- **Tests** — `tests/test_queueing.py`; GS-002 passes; full golden suite green with `LABTRUST_RUN_GOLDEN=1`.

### 2.13 Transport (multi-site)

- **`policy/sites/sites_policy.v0.1.yaml`** — Sites (SITE_HUB, SITE_ACUTE), site_graph, routes (transport_time_mean_s, temp_drift_model, temp_drift_max_c).
- **`src/labtrust_gym/engine/transport.py`** — TransportStore: dispatch(specimen_ids, origin_site, dest_site) → consignment with expected_arrival_ts (deterministic via RNG); tick(now_s) (bounded temp drift); receive(consignment_id); chain_of_custody_sign(consignment_id). Reason codes: TRANSPORT_ROUTE_FORBIDDEN, TRANSPORT_TEMP_EXCURSION, TRANSPORT_CHAIN_OF_CUSTODY_BROKEN. Invariants: INV-COC-001, INV-TRANSPORT-001.
- **Engine** — DISPATCH_TRANSPORT, TRANSPORT_TICK, RECEIVE_TRANSPORT, CHAIN_OF_CUSTODY_SIGN wired in core_env; BLOCKED on forbidden route or temp excursion.
- **Tests** — `tests/test_transport.py` (route legality, determinism, chain-of-custody, temp excursion).

### 2.14 Risk register bundle (contract gate)

- **`src/labtrust_gym/export/risk_register_bundle.py`** — Build RiskRegisterBundle.v0.1 from policy and run dirs; `validate_bundle_against_schema`, **`check_crosswalk_integrity`** (risk_id/evidence_id/control_id referential integrity), **`check_risk_register_coverage`** (required_bench cells evidenced or waived); run-local links normalized to repo-relative paths for portability; when present, TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json are included in links (llm_live pack runs). CLI: `labtrust export-risk-register --out <dir> [--runs <dir_or_glob> ...]`, `labtrust build-risk-register-bundle --out <path>`.
- **Contract gate tests** — `tests/test_risk_register_contract_gate.py`: schema validation of generated bundle, snapshot test (bundle from tests/fixtures/ui_fixtures vs `tests/fixtures/risk_register_bundle_ui_fixtures.v0.1.json`), crosswalk integrity, coverage gate (required (method, risk) evidenced or waived), bundle loadable structure. CI job **risk-register-gate** runs export from tests/fixtures/ui_fixtures then these tests; PRs that break the contract fail CI.
- **External reviewer** — `scripts/run_external_reviewer_risk_register_checks.sh` and `.ps1`: optional security/coord smoke or provided dirs, export-risk-register, schema + crosswalk validation, optional `LABTRUST_STRICT_COVERAGE=1`, optional verify-bundle. See [Risk register](risk_register.md).

### 2.15 Export (receipts, evidence bundle, FHIR R4)

- **`src/labtrust_gym/export/receipts.py`** — load_episode_log, build_receipts_from_log, write_evidence_bundle, export_receipts; Receipt.v0.1 per specimen/result; EvidenceBundle.v0.1 (receipts, episode_log_subset, invariant_eval_trace, enforcement_actions, hashchain_proof, manifest with sha256, optional tool_registry_fingerprint, rbac_policy_fingerprint). CLI: `labtrust export-receipts --run <episode_log.jsonl> --out <dir>`.
- **`src/labtrust_gym/export/verify.py`** — verify_bundle: manifest integrity, schema validation, hashchain proof, invariant trace; when manifest includes them, verifies **tool_registry_fingerprint**, **rbac_policy_fingerprint**, **coordination_policy_fingerprint** (policy/coordination_identity_policy.v0.1.yaml), **memory_policy_fingerprint** (policy/memory_policy.v0.1.yaml).
- **`src/labtrust_gym/export/fhir_r4.py`** — load_receipts_from_dir, receipts_to_fhir_bundle (Specimen, Observation, DiagnosticReport), validate_bundle_structure, export_fhir. CLI: `labtrust export-fhir --receipts <dir> --out <dir>`. Partner overlay: partner_id in Bundle.meta.tag, policy_fingerprint in meta.extension.
- **Schemas** — `policy/schemas/receipt.v0.1.schema.json`, `evidence_bundle_manifest.v0.1.schema.json`, `fhir_bundle_export.v0.1.schema.json`.
- **Tests** — `tests/test_export_receipts.py`, `tests/test_fhir_export.py` (determinism, schema validation, receipt/FHIR coverage).

### 2.16 Package release (release candidate artifact)

- **`src/labtrust_gym/studies/package_release.py`** — run_package_release(profile, out_dir, seed_base): for **minimal**|**full**, runs reproduce then export-receipts and export-fhir per task/condition, copies plots/tables/results, writes MANIFEST.v0.1.json (files + sha256), BENCHMARK_CARD.md, metadata.json. For **paper_v0.1**, runs generate-official-baselines into _baselines/, insider_key_misuse strict_signatures study into _study/, summarize across both, representative run per task with receipts + verify, **security attack suite** (smoke) and **securitization packet** into **SECURITY/** (attack_results.json, coverage.json, coverage.md, reason_codes.md, deps_inventory.json), FIGURES/, TABLES/, RELEASE_NOTES.md, **COORDINATION_CARD.md**, **_coordination_policy/**; deterministic timestamp when seed_base set.
- **CLI** — `labtrust package-release --profile minimal|full|paper_v0.1 --out <dir>` (optional `--seed-base`, `--keep-repro`). `labtrust run-security-suite --out <dir>` runs the security suite and emits SECURITY/ (see docs/security_attack_suite.md). Paper profile: see docs/paper_ready.md.
- **Tests** — `tests/test_package_release.py` (determinism; paper_v0.1 smoke with LABTRUST_PAPER_SMOKE=1); `tests/test_security_attack_suite.py`, `tests/test_securitization.py` (suite determinism, coverage and deps_inventory determinism).
- **CI** — `.github/workflows/package-release-nightly.yml`: scheduled (nightly) and workflow_dispatch; runs package-release --profile minimal; uploads artifact. Not run on normal push/PR.

### 2.17 UI export (UI-ready bundle)

- **`src/labtrust_gym/export/ui_export.py`** — `export_ui_bundle(run_dir, out_zip_path, repo_root)`: detects run type (quick_eval vs package_release), collects tasks/episodes from results and logs, normalizes episode log lines into stable event fields, loads reason code registry from policy; writes a zip with `index.json`, `events.json`, `receipts_index.json`, `reason_codes.json`. UI bundle version **0.1**.
- **CLI** — `labtrust ui-export --run <dir> --out <ui_bundle.zip>`. Accepts labtrust_runs/quick_eval_* or package-release output. See [UI data contract](ui_data_contract.md).
- **Tests** — `tests/test_ui_export.py` (detect run type, normalize event, export from quick_eval fixture, CLI integration, unknown layout raises).
- **UI fixtures** — `tests/fixtures/ui_fixtures/` contains minimal results.v0.2, episode log, evidence bundle, FHIR bundle for offline UI work. UI depends on ui-export output as primary input, not raw internal logs.

### 2.18 Runtime control (shift-change)

- **Engine** — Control actions (processed before RBAC/signature gates, agent_id `SYSTEM`): **UPDATE_ROSTER** merges `args["roster"]` (agent_id → role_id) into in-memory RBAC; **INJECT_SPECIMEN** adds a specimen at runtime via `SpecimenStore.add_specimen(entry)`. Policy on disk is unchanged; RBAC decisions reflect the updated agent→role mapping after UPDATE_ROSTER.
- **`src/labtrust_gym/engine/specimens.py`** — `add_specimen(entry)` adds one specimen at runtime (e.g. for INJECT_SPECIMEN); returns True if added, False if duplicate specimen_id.
- **Emits vocab** — `policy/emits/emits_vocab.v0.1.yaml` includes category **runtime_control** with `UPDATE_ROSTER`, `INJECT_SPECIMEN` in the canonical allowed set.
- **Key registry** — Post-shift keys (e.g. `ed25519:key_reception_analytics`, `ed25519:key_analytics_reception`) in `policy/keys/key_registry.v0.1.yaml` for agent→role mappings after shift change (GS-SHIFT-CHANGE-001).
- **Golden scenario** — **GS-SHIFT-CHANGE-001**: mid-episode UPDATE_ROSTER (swap A_RECEPTION↔A_ANALYTICS roles), INJECT_SPECIMEN (STAT specimen S_STAT), post-shift reception/analytics actions with correct keys, queue_head(DEV_CHEM_A_01)==S_STAT, RELEASE_RESULT by (post-shift) reception → BLOCKED RBAC_ACTION_DENY; strict_signatures: all mutating actions signed.
- **Tests** — `tests/test_golden_suite.py::test_golden_shift_change_001` (runs GS-SHIFT-CHANGE-001 when `LABTRUST_RUN_GOLDEN=1`).

---

## 3. Golden scenarios (34 total)

Golden tests cover engine correctness for core lab workflow, critical v0.2 (escalation ladder), **transport**, **export**, and **runtime control (shift-change)**. Transport/export: **GS-TRANSPORT-001** (dispatch → tick → chain-of-custody sign → receive), **GS-TRANSPORT-002** (temp excursion fault injection → BLOCKED with TRANSPORT_TEMP_EXCURSION and INV-TRANSPORT-001), **GS-COC-003** (chain-of-custody broken), **GS-EXPORT-001** (post_run_hooks: EXPORT_RECEIPTS, VERIFY_BUNDLE, EXPORT_FHIR; asserts output files exist and manifest validates). Shift-change: **GS-SHIFT-CHANGE-001** (mid-episode UPDATE_ROSTER without changing policy on disk; RBAC reflects new agent→role mapping; INJECT_SPECIMEN STAT specimen; queue contract holds; no RELEASE_RESULT from reception role; strict mode — all mutating actions signed).

| Scenario | Title / focus | Passes with engine? |
|----------|----------------|----------------------|
| GS-001 | Full pipeline: accession → accept → move → centrifuge → aliquot → queue → start_run → QC → result → release | ✅ |
| GS-002 | STAT insertion; queue_head(DEV_CHEM_A_01) == 'S2' | ✅ (queue contract v0.1 frozen; see docs/queue_contract.v0.1.md) |
| GS-003 | Citrate underfill → HOLD, INV-COAG-FILL-001 | ✅ |
| GS-004 | ID mismatch → REJECT, ID_MISMATCH | ✅ |
| GS-005 | Leaking → REJECT, INT_LEAKING | ✅ |
| GS-006 | Stability expired → BLOCKED; dual approval mint → START_RUN_OVERRIDE | ✅ |
| GS-007 | Temp out-of-band → BLOCKED TEMP_OUT_OF_BAND | ✅ |
| GS-008 | Restricted door without token → BLOCKED | ✅ |
| GS-009 | Door open too long → ALARM, zone frozen | ✅ |
| GS-010 | Dual approval: same approver twice → BLOCKED INV-TOK-001 | ✅ |
| GS-011 | Expired token → BLOCKED | ✅ |
| GS-012 | Token replay (consumed) → BLOCKED | ✅ |
| GS-013 | Revoked token → BLOCKED | ✅ |
| GS-014 | QC fail → RELEASE_RESULT BLOCKED until rerun | ✅ |
| GS-015 | QC drift override, result_flags contains QC_DRIFT_DISCLAIMER_REQUIRED | ✅ |
| GS-016 | Critical: no release until NOTIFY+ACK; INV-CRIT-004 PASS | ✅ |
| GS-017 | ACK without read-back → INV-CRIT-004:VIOLATION, comm_record_exists | ✅ |
| GS-018 | Downtime → NOTIFY_CRITICAL_RESULT, notification_mode_required | ✅ |
| GS-019 | Agent not in device zone → BLOCKED RC_DEVICE_NOT_COLOCATED | ✅ |
| GS-020 | Illegal move (not on graph) → BLOCKED | ✅ |
| GS-021 | HOLD_SPECIMEN without reason_code → BLOCKED | ✅ |
| GS-022 | Hash chain break → forensic freeze, then all BLOCKED | ✅ |
| GS-CRIT-023 | ACK missing required fields (attempt_id) ⇒ ACK rejected | ✅ |
| GS-CRIT-024 | ESCALATE out of tier order ⇒ blocked | ✅ |
| GS-CRIT-025 | Timeout triggers escalation path; release allowed only after compliant ack | ✅ |
| GS-SIG-026 | Signed actions: mutating action without signature ⇒ BLOCKED SIG_MISSING (strict mode) | ✅ |
| GS-SIG-027 | Signed actions: invalid signature ⇒ BLOCKED SIG_INVALID (strict mode) | ✅ |
| GS-RBAC-028 | RBAC: unauthorized RELEASE_RESULT blocked (reception role cannot release) | ✅ |
| GS-RBAC-029 | RBAC: RELEASE_RESULT_OVERRIDE blocked even with token (token cannot bypass RBAC) | ✅ |
| GS-TRANSPORT-001 | Transport: dispatch → tick → chain-of-custody sign → receive; no violations, receipt-worthy emits | ✅ |
| GS-TRANSPORT-002 | Temp excursion fault injection ⇒ BLOCKED TRANSPORT_TEMP_EXCURSION, INV-TRANSPORT-001 | ✅ |
| GS-COC-003 | Missing/invalid chain-of-custody ⇒ TRANSPORT_CHAIN_OF_CUSTODY_BROKEN, INV-COC-001 | ✅ |
| GS-SHIFT-CHANGE-001 | Mid-episode shift change: UPDATE_ROSTER (RBAC in-memory), INJECT_SPECIMEN (STAT); queue contract; no RELEASE_RESULT from reception; strict signatures | ✅ |
| GS-EXPORT-001 | Post-run hooks: EXPORT_RECEIPTS, VERIFY_BUNDLE, EXPORT_FHIR; output files exist, manifest validates | ✅ |

**Full golden suite:** With `LABTRUST_RUN_GOLDEN=1`, the **full suite passes** (all scenarios; one may be skipped if fixtures unavailable). Queue semantics are frozen in **docs/queue_contract.v0.1.md** (v0.1). Export directories are created under the scenario work dir (e.g. pytest `tmp_path`); Receipt.v0.1 and EvidenceBundle manifest v0.1 are validated during VERIFY_BUNDLE and optional ASSERT_SCHEMA_VALID.

---

## 4. Not included in this repository release (or optional)

### 4.1 Queueing (done; contract frozen)

- **QUEUE_RUN** — Implemented; per-device queue, STAT/URGENT/ROUTINE ordering, co-location, work_id from specimen/accession/aliquot.
- **query(expr): queue_head(device_id)** — Implemented; returns work_id at front or None.
- **START_RUN** — Consumes queue head when no explicit work; strict work_id == queue_head when explicit work.
- **Contract:** **`docs/queue_contract.v0.1.md`** — Frozen; do not weaken (fairness vs. latency vs. safety knob for later work).

### 4.2 Engine modules (from spec)

- **state.py / event.py** — Implemented: `engine/state.py` defines `InitialStateDict` (TypedDict for reset); `engine/event.py` defines `StepEventDict` (TypedDict for step). core_env uses them for `reset(initial_state)` and `step(event)`; sub-stores remain dict-based.
- **clock.py** — Implemented; simulation clock with `set(t_s)` and `advance_to(t_s, completion_callback)`; used in simulated timing mode.
- **rng.py** — Implemented; single RNG wrapper seeded from scenario; used for service-time sampling and determinism.
- **devices.py** — Implemented; DeviceStore with IDLE/RUNNING/FAULT/MAINT; per-device active run and service-time sampling from equipment registry; integrates with START_RUN when `timing_mode: simulated`.
- **queueing.py** — Implemented; DeviceQueue, QueueStore, priority ordering.
- **errors.py** — Reason codes and BLOCKED responses exist; no dedicated error type module.

### 4.3 Policy schemas

- All policy files listed in `POLICY_FILES_WITH_SCHEMAS` have JSON schemas under `policy/schemas/` and are validated by `labtrust validate-policy`: emits vocab, zones, reason codes, token registry, dual approval, critical thresholds, equipment registry, golden scenarios. Runner output contract and test catalogue schemas also exist.

### 4.4 Examples and baselines

- **examples/minimal_random_policy_agent.py** — Present (minimal).
- **examples/scripted_ops_agent.py**, **examples/scripted_runner_agent.py**, **examples/llm_agent_mock_demo.py**, **examples/external_agent_demo.py** — Implemented; use `baselines/scripted_ops.py`, `scripted_runner.py`, `baselines/llm/agent.py`, or plug in via `labtrust eval-agent --agent 'examples.external_agent_demo:MyAgent'`.
- **Benchmark tasks** — throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse (insider + key misuse: 5 phases — forbidden action, forged sig, replay, **revoked key** → SIG_KEY_REVOKED, token misuse) in `benchmarks/tasks.py`; metrics and runner in `benchmarks/`; CLI `labtrust run-benchmark`, `labtrust bench-smoke`, **`labtrust quick-eval`** (throughput_sla, adversarial_disruption, multi_site_stat; 1 episode each; markdown + logs under `labtrust_runs/`). **Results schema split**: v0.2 CI-stable (`results.v0.2.schema.json`, `summary_v0.2.csv`); v0.3 paper-grade (`results.v0.3.schema.json`, quantiles/95% CI, `summary_v0.3.csv`). See [metrics_contract.md](metrics_contract.md).
- **Baselines** — Scripted ops, scripted runner, adversary (`baselines/adversary.py`), **LLM agent** (constrained decoder, rationale required; **DeterministicConstrainedBackend** as official baseline; **canonical allowed-actions payload** in `allowed_actions_payload.py`; **ProviderBackend** and **OpenAILiveBackend** / **OllamaLiveBackend** in `baselines/llm/backends/`; **signing_proxy** for key selection and signing when strict_signatures; **role-aware prompts** via prompt_registry and role_to_prompt; **LLM_DECISION** audit with agent_id, role_id, signed_by_proxy, key_id_used, token counts; **parse_utils** for non-structured backends), PPO via Stable-Baselines3 (`baselines/marl/`; optional `.[marl]`). **run-benchmark --llm-backend deterministic|openai_live|ollama_live**; optional **--llm-agents**; results metadata when LLM used (llm_backend_id, llm_model_id, llm_error_rate, mean_llm_latency_ms, total_tokens, tokens_per_step, p50/p95_llm_latency_ms, estimated_cost_usd). **Prompt-injection golden** scenarios and tests in `policy/golden/prompt_injection_scenarios.v0.1.yaml` and `tests/test_llm_prompt_injection_golden.py`. See docs/llm_live.md and docs/llm_baselines.md. Published benchmark results remain optional.

### 4.5 API and packaging

- **PettingZoo AEC and parallel API** — Implemented; `LabTrustParallelEnv` in `envs/pz_parallel.py`, AEC via `labtrust_aec_env` in `envs/pz_aec.py` (parallel_to_aec). Require `pip install -e ".[env]"`.
- **pip-installable** — Yes (`pyproject.toml`, `pip install labtrust-gym[env,plots]` from PyPI or source). Release workflow (`.github/workflows/release.yml`) builds sdist and wheel on tag `v*`; policy copied into `src/labtrust_gym/policy` before build so wheel ships policy. **labtrust --version** prints version and git SHA. **quick-eval** CLI runs 1 episode each of throughput_sla, adversarial_disruption, multi_site_stat; writes markdown summary and logs under `./labtrust_runs/`. **config.get_repo_root()** resolves policy path (LABTRUST_POLICY_DIR, package data, or repo). MANIFEST.in includes policy for sdist.

### 4.6 Documentation

- **API reference (autogenerated from docstrings)** — Set up via MkDocs + mkdocstrings; included in docs site and deploy to GitHub Pages.
- **Example notebooks (Jupyter)** — None.
- **docs/** — Architecture, policy_pack, threat_model, invariants, benchmarks, ci, pettingzoo_api, queue_contract; this STATUS.

---

## 5. What remains (prioritized)

1. **Queueing and GS-002** — Done. QUEUE_RUN, queue_head, START_RUN consume; full suite green; contract frozen in docs/queue_contract.v0.1.md.

2. **Full golden suite green** — Done. Run with `LABTRUST_RUN_GOLDEN=1`; keep queue contract v0.1 unchanged.

3. **Standard env API** — Done. PettingZoo Parallel and AEC wrappers in `envs/pz_parallel.py`, `envs/pz_aec.py`; observations, actions, rewards, infos; require `.[env]`.

4. **Benchmark tasks and baselines** — Done. Six core tasks (throughput_sla through insider_key_misuse), scripted ops/runner, adversary, insider adversary (insider_key_misuse), LLM agent (mock + deterministic/live backends), PPO/MARL (optional `.[marl]`); `labtrust run-benchmark`, `labtrust bench-smoke`, `labtrust generate-official-baselines`; metrics (throughput, TAT, violations, detection/containment for adversarial_disruption, containment/forensic for insider_key_misuse). Publish empirical results as needed.

5. **Docs and examples** — MkDocs site with mkdocstrings API reference; docs/ expanded (benchmarks, studies, reproduce, enforcement, invariants_registry, marl_baselines, llm_baselines). Jupyter notebooks none.

6. **Optional engine refactor** — state.py and event.py exist (InitialStateDict, StepEventDict used by core_env); errors.py not extracted; clock, rng, devices, queueing exist.

7. **Policy schema coverage** — Done. JSON schemas for emits, zones, reason codes, tokens, dual approval, critical, equipment, golden; all wired into `validate-policy`.

---

## 6. How to run and validate

```bash
# Install (from PyPI or source)
pip install labtrust-gym[env,plots]
# or from source: pip install -e ".[dev]"
labtrust --version

# Quick-eval (1 episode throughput_sla, adversarial_disruption, multi_site_stat; markdown summary + logs under labtrust_runs/)
labtrust quick-eval --seed 42

# Policy validation (all policy files against their JSON schemas)
labtrust validate-policy

# Unit and integration tests (includes golden suite when LABTRUST_RUN_GOLDEN=1)
pytest -q

# Golden suite (full suite with real engine)
LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -v

# PettingZoo + benchmark (optional extra)
pip install -e ".[dev,env,plots]"
pytest tests/test_pz_parallel_smoke.py tests/test_pz_aec_smoke.py tests/test_benchmark_smoke.py tests/test_transport.py tests/test_export_receipts.py tests/test_fhir_export.py tests/test_package_release.py -v
labtrust bench-smoke --seed 42

# Release candidate artifact (reproduce + receipts + FHIR + plots + MANIFEST + BENCHMARK_CARD)
labtrust package-release --profile minimal --out /tmp/labtrust_release --seed-base 100

# Paper-ready artifact (baselines + insider_key_misuse study + FIGURES/TABLES + receipts; see docs/paper_ready.md)
labtrust package-release --profile paper_v0.1 --seed-base 100 --out /tmp/labtrust_paper

# UI-ready zip from a run (quick-eval or package-release output; see docs/ui_data_contract.md)
labtrust ui-export --run ./labtrust_runs/quick_eval_20250115_120000 --out ui_bundle.zip
```

---

## 7. Summary table

| Category | Implemented | Not in this release / optional |
|----------|-------------|----------------------------|
| Policy load/validate | ✅ loader, validate, CLI; JSON schemas for all policy files (emits, zones, reason_codes, tokens, dual_approval, critical, equipment, golden, invariant_registry v1.0, enforcement_map v0.1, runner contract, catalogue) | — |
| Golden runner | ✅ Adapter, runner, emits strict, contract validation | — |
| Audit / hashchain | ✅ Canonical serialization, chain, fault inject, freeze | — |
| Tokens | ✅ Lifecycle, dual approval, replay protection | — |
| Zones / doors | ✅ Graph, doors, device_placement, colocation | — |
| Specimens | ✅ Acceptance, hold/reject, reason codes | — |
| QC | ✅ Device state, result gating, drift override | — |
| Critical | ✅ Classify, notify/ack, downtime path | — |
| Catalogue / stability | ✅ Panel, stability, temp, START_RUN gating | — |
| Co-location | ✅ START_RUN / START_RUN_OVERRIDE device zone check | — |
| Queueing | ✅ queueing.py, QUEUE_RUN, queue_head, START_RUN consume; docs/queue_contract.v0.1.md | — |
| Equipment timing | ✅ devices.py, clock.py, rng.py; timing_mode explicit/simulated; equipment_registry capacity/service_time | — |
| Invariant registry | ✅ policy/invariants/ (registry v1.0), invariants_registry.py, invariants_runtime.py; compiled checks post-step | — |
| Enforcement | ✅ policy/enforcement/enforcement_map; engine/enforcement.py; throttle/kill_switch/freeze_zone/forensic_freeze; step output enforcements | — |
| Engine structure | ✅ core_env + domain modules (audit_log, zones, specimens, qc, critical, queueing, devices, clock, rng, catalogue_runtime, tokens_runtime, invariants_runtime, enforcement) | state.py, event.py, errors.py as separate modules (optional) |
| Env API | ✅ Adapter (reset, step, query); PettingZoo Parallel and AEC wrappers (envs/) | — |
| Baselines / benchmarks | ✅ Scripted ops, scripted runner, adversary; throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse; **coord_scale, coord_risk** (coordination methods: centralized_planner, hierarchical_hub_rr, hierarchical_hub_local, market_auction, gossip_consensus, swarm_reactive, kernel_centralized_edf, kernel_whca, kernel_auction_edf, kernel_auction_whca, kernel_auction_whca_shielded, llm_constrained, marl_ppo; risk_injections with INJ-* and legacy inj_* via NoOpInjector; coordination_scale, blackboard/views/comms, timing, simplex shield); LLM agent (constrained decoder, DeterministicConstrainedBackend, signing_proxy, role-aware prompts, openai_live, ollama_live; LLM_DECISION + token/cost metadata; prompt-injection golden); PPO/MARL (optional [marl]); run-benchmark (--llm-backend, --llm-agents, --coord-method, --injection), bench-smoke, quick-eval, run-study, run-coordination-study, make-plots, reproduce, package-release; episode logging | Published results |
| Studies | ✅ study_runner, plots, reproduce, **package_release**; labtrust run-study, make-plots, reproduce --profile minimal\|full, **package-release --profile minimal\|full\|paper_v0.1 --out \<dir\>** (paper_v0.1: baselines + insider_key_misuse study + FIGURES/TABLES + receipts; see docs/paper_ready.md) | — |
| Transport | ✅ engine/transport.py, sites_policy.v0.1, DISPATCH_TRANSPORT, TRANSPORT_TICK, RECEIVE_TRANSPORT, CHAIN_OF_CUSTODY_SIGN; INV-COC-001, INV-TRANSPORT-001 | — |
| Export | ✅ receipts.py (Receipt.v0.1, EvidenceBundle.v0.1), fhir_r4.py (FHIR R4 Bundle), **ui_export.py** (UI-ready zip: index, events, receipts_index, reason_codes); labtrust export-receipts, export-fhir, **ui-export**; schemas receipt, evidence_bundle_manifest, fhir_bundle_export; docs/ui_data_contract.md | — |
| Risk register | ✅ risk_register_bundle.py (build, validate_bundle_against_schema, check_crosswalk_integrity, check_risk_register_coverage); export-risk-register, build-risk-register-bundle; contract gate tests (schema, snapshot, crosswalk, coverage); CI risk-register-gate; docs/risk_register.md, risk_register_contract.v0.1.md, risk_register_viewer.md; scripts/run_external_reviewer_risk_register_checks.sh and .ps1 | — |
| Security (B008, B009, attack suite) | ✅ **B008:** secret_scrubber, fs_safety, artifact_safety; docs/deployment_hardening.md. **B009:** output_shaping; GET /v0/summary; GET /v0/episode-log admin-only; docs/output_controls.md. **Security attack suite:** policy/golden/security_attack_suite.v0.1.yaml; security_runner.py, securitization.py; SECURITY/ in paper_v0.1; run-security-suite CLI; verify-bundle optional coordination_policy_fingerprint, memory_policy_fingerprint. **Coordination identity:** SignedMessageBus, replay protection; **tool sandbox:** ToolSandbox (egress, data class); **memory hardening:** authenticated writes, poison filtering. **Online:** labtrust serve (authz B007, rate limits); security_online.md | B003 public-release redaction not included in this release |
| Examples | ✅ minimal_random_policy_agent, scripted_ops_agent, scripted_runner_agent, llm_agent_mock_demo, external_agent_demo | — |
| Docs | ✅ README, CONTRIBUTING, STATUS, **installation** (pip, quick-eval, quickstart, troubleshooting), architecture, benchmarks, studies, reproduce, invariants_registry, enforcement, **frozen_contracts** (v0.1.0 freeze), **ui_data_contract** (ui-export), **risk_register** (bundle, generate, review), risk_register_contract.v0.1, risk_register_viewer, marl_baselines, llm_baselines, ci, pettingzoo_api, queue_contract, policy_pack, threat_model, **metrics_contract**; tests/fixtures/ui_fixtures/ for UI; MkDocs site + mkdocstrings API ref; GitHub Pages | Jupyter notebooks |

This STATUS reports the current state of the repo: what is implemented and what remains.

## Implementation and testing audit

Tracks what is **implemented**, **tested**, and what **remains** for official pack v0.2, llm_live transparency, and cross-provider benchmarking.

**Implemented (code):** Pack policy v0.2, transparency log (TRANSPARENCY_LOG/llm_live.json, live_evaluation_metadata.json), official pack runner with prefer_v02, risk register links for llm_live artifacts, anthropic_live backend, run-cross-provider-pack, optional real-backend smoke (llm_live_optional_smoke.yml), E2E artifacts chain CI (package-release to verify-release to export-risk-register).

**Tested:** test_load_benchmark_pack, test_official_pack_smoke_required_folders, test_official_pack_llm_live_writes_transparency_artifacts, test_export_risk_register_from_llm_live_pack (gated by LABTRUST_OFFICIAL_PACK_SMOKE=1), test_cross_provider_contract (same schema per provider).

**Gaps:** No automated end-to-end run with real LLM asserting non-empty model/latency/cost; determinism-report and LABTRUST_RUN_GOLDEN=1 golden suite are separate manual/CI steps. Recommendations: optional CI job for verify-release + export-risk-register on minimal release; document audit in README/CONTRIBUTING.

## Improvements before online (checklist)

Before adding online APIs and non-deterministic runs: (1) **Stability:** fix tests/fixtures/ui_fixtures evidence bundle for verify-bundle; stabilize long-running tests (timeout or @pytest.mark.slow); decide golden suite in CI; determinism-report coverage. (2) **Code:** policy loading in hot path; policy path resolution; large JSONL handling; single-pass summarize/export; no ambient randomness. (3) **Testing:** pytest timeout and @pytest.mark.slow for package_release/golden; coverage; CI matrix Linux/Windows; smoke script. (4) **Docs/UX:** path with special characters; quickstart robustness; CLI error clarity. (5) **Pre-online:** deterministic baseline stays default; real LLM behind a flag; API keys from environment only; non-deterministic runs clearly labeled. See [Deterministic vs non-deterministic runs](ci.md#deterministic-vs-non-deterministic-runs) and [Contributing](contributing.md) for verification and audit steps.

For a structured view of **current state, gaps, what to work on next, what demands attention, and what is not yet state-of-the-art**, see [Current state and priorities](CURRENT_STATE_AND_PRIORITIES.md).
