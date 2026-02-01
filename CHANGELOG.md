# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- **Key registry lifecycle**: Optional fields in `policy/schemas/key_registry.v0.1.schema.json`: **status** (ACTIVE, REVOKED, EXPIRED; default ACTIVE), **not_before_ts_s** / **not_after_ts_s** (validity window). Signature verification (`engine/signatures.py`) checks: key exists; status ACTIVE (or omitted); now_ts in [not_before_ts_s, not_after_ts_s]; key bound to event agent_id; Ed25519 verify. Reason codes: **SIG_KEY_REVOKED**, **SIG_KEY_EXPIRED**, **SIG_KEY_NOT_YET_VALID**. `policy/keys/key_registry.v0.1.yaml` includes revoked key `ed25519:key_revoked` for TaskF. **TaskF phase 4**: insider uses revoked key_id → BLOCKED with SIG_KEY_REVOKED. TaskF runs with **strict_signatures: True**. Tests: `tests/test_signatures_key_lifecycle.py` (valid/revoked/expired/not-yet-valid). Docs: `docs/policy_pack.md` (keys section with lifecycle semantics).

- **LLM constrained baseline**: Policy summary schema extended (`policy/llm/policy_summary.schema.v0.1.json`: key_constraints, critical_ladder_summary, restricted_zones, token_requirements); **generate_policy_summary_from_policy()** in `shield.py`. **Constrained action decoder** (`baselines/llm/decoder.py`): schema + **rationale required** + allowed_actions at decode time; MISSING_RATIONALE, RBAC/zone checks. **DeterministicConstrainedBackend(seed)** as official LLM baseline: chooses from allowed_actions with seeded RNG; same seed ⇒ same action sequence. `run_benchmark(..., use_llm_safe_v1_ops=True)` uses DeterministicConstrainedBackend. Tests: `tests/test_llm_constrained_decoder.py` (illegal action/missing rationale rejected; deterministic). Docs: `docs/llm_baselines.md` (deterministic vs non-deterministic, plug real provider behind flag).

- **Publishability (PyPI packaging, quick-eval, versioning):** PyPI-ready packaging: `pyproject.toml` metadata (classifiers, maintainers, package_data for policy), MANIFEST.in (policy, README, LICENSE). `labtrust --version` / `-V` prints version and git SHA. **quick-eval** CLI: 1 episode each of TaskA, TaskD, TaskE; markdown summary and logs under `./labtrust_runs/` (`--seed`, `--out-dir`). **config.get_repo_root()** resolves policy path (LABTRUST_POLICY_DIR, package data, or repo); CLI and runner use it so policy works from repo and from installed wheel. Release workflow (`.github/workflows/release.yml`) on tag `v*`: copy policy into `src/labtrust_gym/policy`, build sdist and wheel, upload artifacts; publish job structure (twine; add secrets to enable). CI **quick-eval** job: install `.[env,plots]`, run `labtrust quick-eval`. **docs/installation.md** (pip, quick-eval, development). README and docs updated: Installation (pip), Quick eval, CLI quick-eval and --version, layout (config.py, version.py), STATUS, CONTRIBUTING, ci.md (quick-eval job, release workflow), index.md (CLI table, layout).

- **LLM agent interface**: Offline-safe, deterministic-by-default. `baselines/llm/agent.py`: `LLMBackend` protocol (generate(messages)->text), `LLMAgent` (system prompt, backend call, strict JSON parse + schema validation). Backends: `MockDeterministicBackend` (canned JSON from observation hash), `OpenAIBackend` stub (API key from env; not used in tests). Action schema `policy/llm/action_schema.v0.1.json`; validate proposed action JSON. Example `examples/llm_agent_mock_demo.py` (TaskB with LLMAgent(mock) + scripted runners). Tests `tests/test_llm_agent_mock.py` (deterministic mock, schema validation). Docs `docs/llm_baselines.md`.

- **PPO (MARL) baseline**: Optional extra `[marl]` with stable-baselines3 and gymnasium. `baselines/marl/sb3_wrapper.py`: Gymnasium wrapper for single-agent PPO (ops_0 controlled; runners scripted). `ppo_train.py`: train PPO on TaskA with fixed seeds, save model and eval metrics. `ppo_eval.py`: evaluate trained policy for N episodes with deterministic seeds. CLI: `labtrust train-ppo --task TaskA --timesteps 50000 --seed 123 --out runs/ppo`, `labtrust eval-ppo --model ... --episodes 50 --seed 123`. Smoke test guarded by `LABTRUST_MARL_SMOKE=1` (not default CI). Docs: `docs/marl_baselines.md`.

- **Policy-driven enforcement**: `policy/enforcement/enforcement_map.v0.1.yaml` with rules matching violations by invariant_id/severity/scope; actions throttle_agent, kill_switch, freeze_zone, forensic_freeze; escalation (first violation -> throttle, repeated -> kill_switch/freeze_zone). Schema `enforcement_map.v0.1.schema.json` and validate-policy wiring. Engine `enforcement.py` consumes violations, applies actions deterministically, records to audit log. Step output includes `enforcements` list. Gate via `enforcement_enabled` in reset initial_state (default false; golden suite unchanged). Docs: `docs/enforcement.md`; tests: `tests/test_enforcement.py`.

- Repo layout: `policy/` (schemas for all policy files, emits, invariants, tokens, reason_codes, zones, catalogue, stability, equipment, critical, golden), `src/labtrust_gym/` (engine, policy, runner, envs, baselines, benchmarks, logging, cli), `tests/`, `examples/`, `docs/`.
- Golden runner and adapter interface: `LabTrustEnvAdapter`, `GoldenRunner`, emits vocabulary validation (unknown emits fail). Full golden suite passes with real engine.
- CLI: `labtrust validate-policy` (all policy files validated against JSON schemas), `labtrust run-benchmark`, `labtrust bench-smoke`.
- CI: ruff format/check, mypy, pytest, policy validation; optional bench-smoke (nightly/manual).
- Apache-2.0 license, README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY.
- **docs/STATUS.md** — Current state: policy schemas (emits, zones, reason_codes, tokens, dual_approval, critical, equipment, golden), hashchain, tokens, zones, specimens, QC, critical, catalogue/stability, co-location, queueing, devices/clock/rng, PettingZoo Parallel/AEC, scripted baselines, benchmark harness, episode logging.
- JSON schemas for all policy YAML/JSON (emits vocab, zones, reason codes, token registry, dual approval, critical thresholds, equipment registry, golden scenarios); wired into `validate-policy`; tests for invalid policy failing.
- Engine: audit hashchain and forensic freeze (GS-022); token lifecycle and dual approval (GS-010–013); zones and doors (GS-008, GS-009, GS-020); specimen acceptance (GS-003–005, GS-021); QC and result gating (GS-014, GS-015); critical results notify/ack (GS-016–018); catalogue and stability START_RUN gating (GS-001, GS-006, GS-007); co-location (GS-019); queueing QUEUE_RUN/queue_head/START_RUN consume (GS-002); equipment timing (devices, clock, rng; timing_mode explicit/simulated).
- PettingZoo Parallel and AEC wrappers (`envs/pz_parallel.py`, `envs/pz_aec.py`); scripted ops and scripted runner baselines; benchmark tasks (TaskA, TaskB, TaskC), metrics, runner; episode logging (JSONL).

## [0.1.0] - TBD

- Initial policy-first layout and golden suite scaffolding.
- Runner output contract schema and golden scenarios (15–22 scenarios).
- Emits vocab and strict validation in runner.
