# Frozen contracts

This page is the **canonical list of frozen contracts and schema versions** for LabTrust-Gym. These define correctness and the anti-regression backbone; do not weaken them without an explicit design change and version bump.

| Contract / schema | Version | Location | Purpose |
|------------------|---------|----------|---------|
| **Runner output contract** | v0.1 | `policy/schemas/runner_output_contract.v0.1.schema.json` | Shape of each `step()` return: `status`, `emits`, `violations`, `blocked_reason_code`, `token_consumed`, `hashchain`, optional `state_snapshot`. Golden runner and engine must conform. |
| **Queue contract** | v0.1 | [queue_contract.v0.1.md](queue_contract.v0.1.md) | Device queue semantics: item fields, priority ordering (STAT/URGENT/ROUTINE), `QUEUE_RUN` / `START_RUN` interaction, meaning of `queue_head(device_id)`. Fairness vs. latency vs. safety knob. |
| **Invariant registry schema** | v1.0 | `policy/schemas/invariant_registry.v1.0.schema.json` | Schema for `policy/invariants/invariant_registry.v1.0.yaml`: invariant_id, title, severity, scope, signals, logic_template, exception_hooks, enforcement_hint. |
| **Enforcement map schema** | v0.1 | `policy/schemas/enforcement_map.v0.1.schema.json` | Schema for `policy/enforcement/enforcement_map.v0.1.yaml`: rules matching invariant_id/severity/scope → actions (throttle_agent, kill_switch, freeze_zone, forensic_freeze); escalation tiers. |
| **Study spec (run-study)** | v0.1 | `policy/studies/*.yaml` (e.g. `study_spec.example.v0.1.yaml`); structure implied by run-study loader | Study specs: task, episodes, seed_base, ablations; used by `labtrust run-study` for reproducible experiment definitions. No separate JSON schema in repo. |
| **Receipt schema** | v0.1 | `policy/schemas/receipt.v0.1.schema.json` | Per-specimen/result receipt (identifiers, timestamps, decision, reason_codes, tokens, invariant/enforcement summary, hashchain). Used by export-receipts. |
| **Evidence bundle manifest schema** | v0.1 | `policy/schemas/evidence_bundle_manifest.v0.1.schema.json` | Manifest for EvidenceBundle.v0.1: files (path, sha256), policy_fingerprint, partner_id. |
| **FHIR bundle export schema** | v0.1 | `policy/schemas/fhir_bundle_export.v0.1.schema.json` | Minimal structural contract for FHIR R4 Bundle export (resourceType, type, entry). Not full FHIR validation. |
| **Sites policy schema** | v0.1 | `policy/schemas/sites_policy.v0.1.schema.json` | Schema for `policy/sites/sites_policy.v0.1.yaml`: sites, site_graph, routes (transport_time, temp_drift). Used by engine/transport. |
| **Key registry schema** | v0.1 | `policy/schemas/key_registry.v0.1.schema.json` | Schema for `policy/keys/key_registry.v0.1.yaml`: Ed25519 keys (key_id, public_key, agent_id, role_id); optional status (ACTIVE/REVOKED/EXPIRED), not_before_ts_s, not_after_ts_s. Used by engine/signatures; lifecycle enforced in verification. |
| **RBAC policy schema** | v0.1 | `policy/schemas/rbac_policy.v0.1.schema.json` | Schema for `policy/rbac/rbac_policy.v0.1.yaml`: roles (allowed_actions, allowed_zones, allowed_devices), agents (agent_id → role_id), action_constraints. Used by engine/rbac. |
| **Action contract** | v0.1 | `src/labtrust_gym/envs/action_contract.py` | Per-step action: `action_index` in 0..5; optional `action_type`, `args`, `reason_code`, `token_refs`. Coordination methods and risk injectors must use these indices. |
| **Env contract (BenchmarkEnv)** | v0.1 | `src/labtrust_gym/benchmarks/env_protocol.py` | New envs must implement `BenchmarkEnv`. The benchmark runner depends only on this protocol; it does not use private attributes (`_device_ids`, `_zone_ids`, `_dt_s`). |
| **Coordination baseline contract** | v0.1 | `src/labtrust_gym/baselines/coordination/interface.py` | Defines the coordination *method* interface; "baseline" here means reference implementation, not the v0.2 frozen result set. Required: `reset(seed, policy, scale_config)`, `propose_actions(obs, infos, t)` → one action per agent with `action_index` in 0..5. Optional: `on_step_result`, `on_episode_end`. Enforced by `tests/test_coordination_interface_contract.py`: every method_id in `coordination_methods.v0.1.yaml` instantiates, runs 5 steps coord_scale, returns schema-valid actions and is deterministic. Conformance to this contract (schema-valid, deterministic) does not imply that the method's outputs are safe or correct; safety is a separate concern. |
| **Benchmark results schema** | v0.2 | `policy/schemas/results.v0.2.schema.json` | CI-stable benchmark results: task, seeds, policy_fingerprint, partner_id, git_sha, agent_baseline_id, episodes with metrics (ints/structs). Used by run-benchmark output and summarize-results; summary_v0.2.csv regression is stable across OS/Python. |
| **Benchmark results schema** | v0.3 | `policy/schemas/results.v0.3.schema.json` | Paper-grade extension of v0.2: optional quantiles, 95% CI, simulated-mode distributions. Same required fields as v0.2; summary_v0.3.csv includes quantiles and CI. See [Metrics contract](metrics_contract.md). |

## Runner output contract (v0.1)

The engine and any adapter implementing `LabTrustEnvAdapter` must return step results that validate against `policy/schemas/runner_output_contract.v0.1.schema.json`. Key fields:

- `status`: `"ACCEPTED"` or `"BLOCKED"`
- `emits`: list of emit strings (must be in `policy/emits/emits_vocab.v0.1.yaml`)
- `violations`: list of `{ invariant_id, status, reason_code }`
- `blocked_reason_code`: present when `status == "BLOCKED"`; must be in reason code registry
- `token_consumed`: list of token IDs consumed this step
- `hashchain`: `{ head_hash, length, last_event_hash }` (append-only; chain break → forensic freeze)

Validated in CI via `labtrust validate-policy` and by the golden runner against step outputs.

## Queue contract (v0.1)

Behavioral contract for device queues: see [Queue contract v0.1](queue_contract.v0.1.md). Covers `DeviceQueueItem` fields, priority ordering, `QUEUE_RUN` validation, `START_RUN` consuming queue head, and `query('queue_head(device_id)')`. Golden scenario GS-002 and queueing tests depend on it.

## Invariant registry schema (v1.0)

Defines the structure of the machine-readable invariant registry (`policy/invariants/invariant_registry.v1.0.yaml`). Used by `labtrust validate-policy` and by `invariants_runtime` to compile and evaluate invariants post-step.

## Enforcement map schema (v0.1)

Defines the structure of the enforcement map (`policy/enforcement/enforcement_map.v0.1.yaml`). Maps violation conditions to actions (throttle, kill_switch, freeze_zone, forensic_freeze). Validated by `labtrust validate-policy`; consumed by `engine/enforcement.py`.

## Study spec (run-study) (v0.1)

Study specification YAMLs (e.g. `policy/studies/study_spec.example.v0.1.yaml`) define task, episodes, seed_base, ablations, and agent_config. The run-study loader parses these; there is no separate JSON schema file in the repo. Used by `labtrust run-study` to expand ablations and run benchmark conditions. Ensures reproducible experiment definitions.

## Receipt and evidence bundle (v0.1)

Receipt and evidence bundle manifest schemas define the shape of exported receipts (per specimen/result) and the EvidenceBundle.v0.1 manifest (files + sha256, policy_fingerprint). When the run used LLM coordination and the episode log contains proposal_hash / shield_outcome_hash or LLM_COORD_AUDIT_DIGEST, the manifest may include optional **coordination_audit_digest_sha256**; verify-bundle checks it when present. Validated when exporting; see [Enforcement](../policy/enforcement.md) (evidence bundle section) and [FHIR R4 export](../export/fhir_export.md).

## FHIR bundle export (v0.1)

Minimal structural contract for FHIR R4 Bundle export (resourceType Bundle, type collection, entry with fullUrl and resource). Not full FHIR profile validation. See [FHIR R4 export](../export/fhir_export.md).

## Sites policy (v0.1)

Schema for `policy/sites/sites_policy.v0.1.yaml`: sites, site_graph, routes (transport_time_mean_s, temp_drift). Used by `labtrust validate-policy` and engine/transport.

## Action contract (v0.1)

Per-step action: `action_index` in 0..5 (see [envs/action_contract.py](https://github.com/fraware/LabTrust-Gym/blob/main/src/labtrust_gym/envs/action_contract.py)); optional `action_type`, `args`, `reason_code`, `token_refs`. All coordination methods and risk injectors must use these indices. The runner converts action dicts to `(actions, action_infos)` and passes them to `env.step(actions, action_infos)`.

## Env contract (BenchmarkEnv) (v0.1)

New envs must implement `BenchmarkEnv` (see `src/labtrust_gym/benchmarks/env_protocol.py`). The benchmark runner depends only on this protocol; it does not use private attributes (`_device_ids`, `_zone_ids`, `_dt_s`).

**PettingZoo env (LabTrustParallelEnv):** The wrapper implements the full Parallel API including **render()** (modes ansi/human when `render_mode` is set), **reset(seed, options)** with optional `timing_mode` and `dt_s` in options, and observation building via batch **get_agent_zones** / **get_agent_roles** when the engine supports them. The engine may implement optional **step_batch(events)** (same semantics as calling step(e) for each event in order); the PZ env uses it when available. For flat observations per agent, use **FlattenObsWrapper** (`labtrust_gym.baselines.marl`). See [PettingZoo API](../agents/pettingzoo_api.md).

## Coordination baseline contract (v0.1)

Every coordination method registered in `policy/coordination/coordination_methods.v0.1.yaml` must implement the interface in `src/labtrust_gym/baselines/coordination/interface.py` (CoordinationMethod): **reset(seed, policy, scale_config)** and **propose_actions(obs, infos, t)** returning a dict of agent_id to action_dict with at least **action_index** (int in 0..5). Optional hooks: **on_step_result(step_outputs)**, **on_episode_end(episode_metrics)**, **combine_submissions(submissions, obs, infos, t)**. The **combine_submissions** method combines per-agent submissions into a joint action dict; default implementation treats each submission as an action_dict and fills missing agents with NOOP. **For N <= N_max, only propose_actions (or step) is used; combine_submissions is never called.** At scale (simulation-centric when N > coord_propose_actions_max_agents, default 50), the runner uses per-agent submissions and **combine_submissions** only; **propose_actions** is not called. In agent-centric multi-agentic mode, the driver also uses **combine_submissions**. The set of methods that receive per-agent LLM at scale (scale-capable) is defined in policy (coordination_methods.v0.1.yaml, optional scale_capable: true) with a fallback for existing configs; see [design_choices §6.3](../architecture/design_choices.md). New methods cannot break CI: `pytest tests/test_coordination_interface_contract.py` loads every method_id, instantiates via registry (deterministic backends; no network), runs 5 steps in coord_scale with seed=42, and asserts actions for all agents, schema-valid proposals, and determinism. Conformance to this contract does not imply that the method's outputs are safe or correct; safety is a separate concern. See [Coordination methods](../coordination/coordination_methods.md).

## Acceptance (v0.2.0 release)

A fresh machine can run:

```bash
pip install labtrust-gym[env,plots]
labtrust --version          # prints v0.2.0 + git SHA
labtrust quick-eval --seed 42
labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>
labtrust verify-bundle --bundle <bundle_dir>   # passes when bundle is from export-receipts
```

Use an EvidenceBundle path under `receipts/` (e.g. `receipts/taska_cond_0/EvidenceBundle.v0.1`), not the release root. To verify all bundles in a release: `labtrust verify-release --release-dir <path>`. See [Trust verification](../risk-and-security/trust_verification.md) for the full trust story and how to run each verification step.

## Release artifacts (v0.2.0)

Attach to GitHub Release (tag v0.2.0):

- **wheel + sdist** — Built by `.github/workflows/release.yml` on tag `v*`. `pip install labtrust-gym[env,plots]` from PyPI or from the wheel.
- **SHA256SUMS.txt** (wheel + sdist) and **policy tarball** (filename `policy-bundle-vX.Y.Z.tar.gz` matching the git tag) — Built into `release-assets/` on the same tag push and attached to the GitHub Release by the workflow (not published to PyPI).
- **paper_v0.1 package-release artifact** — Run `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>`; zip the output (FIGURES/, TABLES/, receipts, **SECURITY/** (attack_results.json, coverage.json, coverage.md, reason_codes.md, deps_inventory.json), RELEASE_NOTES.md, **COORDINATION_CARD.md**, **_coordination_policy/** with frozen coordination policy + manifest, etc.) or link to immutable storage.
- **Determinism reports** — Run `labtrust determinism-report --task throughput_sla --episodes 2 --seed 42 --out <dir>` for explicit and (if supported) simulated; attach determinism_report.md and determinism_report.json.

## LLM prompt-injection golden scenarios

Adversarial strings are injected into untrusted_notes (e.g. specimen.note, transport manifest note) and passed to the LLM context. The golden suite asserts that constraints are not bypassed:

- **action_type** must be from **allowed_actions** or **NOOP** (decoder + shield).
- **Blocked/violations threshold:** When prompt injection is present, blocked count and violations must not increase vs baseline beyond the documented deltas. In tests: `PROMPT_INJECTION_BLOCKED_DELTA_MAX = 0`, `PROMPT_INJECTION_VIOLATIONS_DELTA_MAX = 0`. Scenarios are defined in `policy/golden/prompt_injection_scenarios.v0.1.yaml`; tests in `tests/test_llm_prompt_injection_golden.py`.

## Quickstart script

From repo root: `bash scripts/quickstart_paper_v0_1.sh` (or `scripts/quickstart_paper_v0.1.ps1` on Windows). Runs: install → validate-policy → quick-eval → package-release paper_v0.1 → verify-bundle.

## UI data contract

The **ui-export** output is the primary input for the UI. Run `labtrust ui-export --run <dir> --out ui_bundle.zip` to produce a zip containing `index.json`, `events.json`, `receipts_index.json`, and `reason_codes.json`. Schema version: **UI bundle v0.1**. See [UI data contract](ui_data_contract.md) for folder layouts (labtrust_runs, package-release), required files, relationships, and schema version handling. The UI must not depend on raw internal logs.

## Extensibility

New domains, tasks, coordination methods, invariant handlers, security/safety providers, and metrics aggregators are **additive** and must conform to the existing contracts: adapter interface (`LabTrustEnvAdapter`), task interface (`BenchmarkTask`), coordination interface (`CoordinationMethod`), invariant registry schema (v1.0), and results v0.2/v0.3 semantics. Registration is via `register_*` APIs or setuptools entry_points; see [Extension development](../agents/extension_development.md). Frozen contracts (runner output, queue, receipt, evidence bundle, etc.) are unchanged; extensions only add new names or optional fields.

---

See also: [Policy pack and schemas](../policy/policy_pack.md), [Installation](../getting-started/installation.md), [Paper provenance](../benchmarks/paper/README.md).
