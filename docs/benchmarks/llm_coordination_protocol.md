# LLM Coordination Protocol

This document defines the benchmark protocol for LLM-based coordination methods in LabTrust-Gym: pipeline modes, typed proposal schema, shield semantics, repair loop policy, logging and verification, security evaluation across the risk taxonomy, and reporting format. It enables external reviewers to run coordination studies with `--llm-backend deterministic` (no network) and verify bundles and coverage gates offline.

## Coordination methods are LLM-based

In this repo, **coordination methods** are defined as **LLM-based**: they are ways for LLM agents to work together. The goal of having multiple coordination methods is to **compare LLM-based coordination strategies on the same baseline** (same tasks, scales, injections). Methods with `llm_based: true` in `policy/coordination/coordination_methods.v0.1.yaml` (or `coordination_class: llm`) are the coordination methods used for comparison. Kernel and deterministic algorithms (e.g. `kernel_whca`, `market_auction`) have `llm_based: false`; they exist as baseline components or as building blocks inside LLM methods (e.g. the kernel inside `llm_repair_over_kernel_whca`), but they are not coordination methods for comparison. The default pipeline without coordination is the deterministic (scripted) pipeline. Use `--methods-from full_llm` when running the coordination security pack to run only LLM-based coordination methods.

## Pipeline modes

| Mode | Description | Network | LLM usage |
|------|-------------|---------|-----------|
| **deterministic** | Scripted agents only; no LLM interface. Default for CI and regression. | Forbidden | None |
| **llm_offline** | LLM agent/coordination interface with deterministic backend only (seeded proposals, no API). | Forbidden | Deterministic backend (e.g. NOOP / seeded) |
| **llm_live** | Allows network-backed LLM backends (e.g. openai_live). Requires explicit `--allow-network` or `LABTRUST_ALLOW_NETWORK=1`. | Allowed when opted in | Live API (opt-in only) |

- **Default**: All commands (`run-benchmark`, `run-coordination-study`, `package-release`) default to **deterministic**. No OpenAI or other external API is called unless the user explicitly passes `--llm-backend openai_live` (and, for openai_live, `OPENAI_API_KEY` must be set or the run fails with reason code `OPENAI_API_KEY_MISSING`).
- **Gating**: In `llm_live`, `check_network_allowed()` is invoked before any live API call; if network is not allowed, a `RuntimeError` is raised with a clear message.
- **Reproducibility**: With `--llm-backend deterministic`, same `seed_base` and same coordination policy fingerprint yield identical `summary_coord.csv` and cell results. Deterministic tests remain offline.
- **llm_offline fault model**: In `llm_offline` mode, an optional deterministic fault model can wrap the repair backend to inject simulated failures (invalid_output, empty_output, high_latency, inconsistent_plan); fallback is NOOP with recorded reason codes. See [Live LLM – llm_offline fault model](../agents/llm_live.md#llm_offline-fault-model).

## Local-decider flow (llm_local_decider_signed_bus)

**llm_local_decider_signed_bus** uses a per-agent local view and a signed bus:

1. **Local view**: For each worker, a strictly bounded observation slice is built (zone_id, step_id, queue_summary with capped device count and string lengths). No global state; view size is bounded (e.g. MAX_LOCAL_VIEW_BYTES).

2. **ActionProposal**: Each agent’s backend (LLM or deterministic) produces an **ActionProposal** (action_type, args, reason_code, confidence, safety_notes) conforming to the existing ActionProposal schema. The proposal is the payload of a coordination message.

3. **Sign and publish**: Proposals are signed (sender_id, nonce, epoch, message_type, payload, signature) and submitted to **SignedMessageBus**. Message type is `action_proposal`.

4. **Signature and epoch gating**: The bus rejects any message that fails signature verification or epoch binding. Rejected messages are not delivered. Counters: **invalid_sig_count**, **replay_drop_count** (nonce already seen), **spoof_attempt_count** (signature verifies with a different agent’s key than the claimed sender_id).

5. **Reconciliation**: Accepted proposals are passed to a **deterministic reconciler** that resolves conflicts (e.g. two agents claiming the same device or queue head). One winner per resource; overridden proposals are turned into NOOP. **conflict_rate** = fraction of proposals overridden.

6. **Shield**: The final joint action set is executed by the runner; the env/shield applies RBAC and signature checks as usual. No separate simplex shield in the method; the engine blocks invalid actions.

**Metrics**: coordination.comm is extended with **invalid_sig_count**, **replay_drop_count**, **invalid_msg_rate**, **spoof_attempt_count**. coordination.alloc has **conflict_rate**, **overridden_count**, **total_proposals**. When the method provides get_comm_metrics(), the runner merges these into the episode coordination.comm block.

**coord_risk**: With INJ-ID-SPOOF-001 and strict signatures, spoofed actions are rejected by the bus or engine; attack_success_rate should be near 0. With INJ-COMMS-POISON-001, detection signals (invalid_sig_count, replay_drop_count) may increase; runs remain stable and deterministic offline.

## Typed proposal schema

LLM-based coordination methods produce **CoordinationProposal** objects conforming to `policy/schemas/coordination_proposal.v0.1.schema.json`.

- **Required fields**: `proposal_id`, `step_id`, `method_id`, `per_agent`, `comms`, `meta`.
- **per_agent**: Array of per-agent entries; each has `agent_id`, `action_type`, `args`, `reason_code`; optional `confidence`, `token_refs`.
- **comms**: Array of proposed messages; each has `from_agent_id`, `channel`, `payload_typed`, `intent`, `ttl_steps`; optional `to_agent_id`, `broadcast`.
- **meta**: Audit fields: `prompt_fingerprint`, `policy_fingerprint`, `backend_id`, `model_id`, `latency_ms`, `tokens_in`, `tokens_out` (optional but recommended for live backends).

Live backends (e.g. OpenAI Responses API) use structured outputs constrained to this schema. Validation runs before execution; invalid proposals can trigger the repair loop (see below).

## Shield semantics

- **Runtime shield**: Before execution, each proposed action is passed through a **shield** (RBAC + capability + signature checks). The shield returns `(safe_action, filtered, block_reason)`.
- **Blocked actions**: Actions that fail the shield are not executed; they are recorded with `blocked_reason_code` (e.g. `RBAC_ACTION_DENY`, `SIG_INVALID`, `PROMPT_INJECTION_DETECTED`) and contribute to `safety.blocks_total` and per-step blocked counts.
- **Simplex-style wrapping**: Optional method `kernel_auction_whca_shielded` wraps an advanced coordination method with a Simplex-style shield; when the shield rejects the advanced plan, a fallback (e.g. safe default) is used. `last_shield_emits` are recorded for audit.
- **Telemetry**: Step results and episode metrics include `safety_shield_applied` and optional `safety_shield_details`; coordination study summary includes `blocked_rate` and `repair_rate` for LLM methods.

## Repair loop policy and caps

- **Purpose**: When the shield blocks one or more actions from a proposal, the runner can feed a **RepairRequest** back to the coordinator (e.g. LLM) and retry.
- **RepairRequest**: Contains `blocked_reason_codes`, `failed_validation_fields`, and a `state_digest` (step, attempt, blocked_count, etc.).
- **Caps**: `max_repairs` (default 1) limits retries: total attempts = 1 + max_repairs. After the cap, the last report is used and no further proposal is requested for that step.
- **Success condition**: Execution stops retrying when `len(blocked_actions) <= blocked_threshold` (typically 0).
- **Configuration**: `max_repairs` and `blocked_threshold` are configurable via scale_config (e.g. in the coordination study spec or task scale). When building LLM coordination methods (e.g. llm_central_planner), the registry reads `scale_config.get("max_repairs", 1)` and `scale_config.get("blocked_threshold", 0)` and passes them into the method constructor; they may be overridden again at `reset(seed, policy, scale_config)` per episode.
- **Validation failure**: If a proposal fails schema/validation before execution, the repair request carries `failed_validation_fields`; the coordinator may resubmit a valid proposal on the next attempt.
- **Logging**: Each attempt is logged with `log_type: LLM_COORD_PROPOSAL_ATTEMPT`, `proposal_hash`, `repair_request_hash`, `shield_outcome_hash`, `validation_failed`, and `blocked_count` for auditing and reproducibility.

## What gets logged and verified

- **Episode log (JSONL)**: When `--log` is set, each step can emit entries including `LLM_COORD_PROPOSAL` (per-step proposal hash and meta: latency_ms, tokens_in, tokens_out, estimated_cost_usd, backend_id, model_id for auditing) and `LLM_COORD_PROPOSAL_ATTEMPT` (attempt index, hashes, validation/blocked outcome when the repair loop is used). Redacted proposal payloads may be logged at DEBUG for auditing; secrets are never logged (secret_scrubber).
- **Results metadata**: For runs using a live or deterministic LLM coordination backend, `results.metadata` includes `llm_backend_id`, `llm_model_id`, `mean_llm_latency_ms`, `p50_llm_latency_ms`, `p95_llm_latency_ms`, `tokens_per_step`, `estimated_cost_usd`, `llm_error_rate` when available.
- **Verify-bundle**: After exporting receipts, `labtrust verify-bundle --bundle <dir>` runs integrity and policy checks on the evidence bundle. External reviewers can run this on package-release or coordination-study outputs without network.
- **Coverage gates**: The coordination study spec and method-risk matrix define which (method, risk) cells are required; summary_coord.csv and pareto.md support reviewing coverage (see Reporting format below). The external reviewer script runs a coverage check: every cell with `required_bench: true` in the method-risk matrix must have at least one row in summary_coord.csv (by method_id and risk_id). By default missing cells are reported and the script exits 0; set **LABTRUST_STRICT_COVERAGE=1** to exit 1 when any required cell is missing.
- **Audit digest and determinism**: When LLM coordination is used and `--log` is set, the episode log includes per-step `LLM_COORD_PROPOSAL` lines (with `canonical_proposal_hash` and `shield_outcome_hash`) and an end-of-episode `LLM_COORD_AUDIT_DIGEST` line. The runner computes `shield_outcome_hash` from step results after `env.step` (single-shot path) or from the repair report when the repair loop is used. The digest has `audit_digest_version` (e.g. `"0.1"`), `episode_id`, and `steps`: a list of `{step_id, proposal_hash, shield_outcome_hash}`. Deterministic runs (same seed, same coord method, deterministic backend) produce identical proposal_hash and shield_outcome_hash sequences; the determinism test compares audit digest steps across two runs.

## Security evaluation: mapping risks to injections/tests

- **Risk taxonomy**: Risks are defined in policy (e.g. `method_risk_matrix.v0.1.yaml`, `injections.v0.2.yaml`). Each injection has `injection_id`, `strategy_type`, `success_definition`, `detection_definition`, `containment_definition`.
- **Mapping**: coord_risk applies one injection per cell. The study spec lists `injections` (e.g. `INJ-ID-SPOOF-001`, `INJ-COMMS-POISON-001`, `INJ-BID-SPOOF-001`, `INJ-LLM-PROMPT-INJECT-COORD-001`). The risk harness applies them deterministically given the cell seed.
- **LLM-relevant injections** (from `policy/coordination/injections.v0.2.yaml`): Include prompt injection (`INJ-LLM-PROMPT-INJECT-COORD-001`), tool escalation (`INJ-LLM-TOOL-ESCALATION-001`), comms flood (`INJ-COMMS-FLOOD-LLM-001`), replay (`INJ-ID-REPLAY-COORD-001`), collusion/market (`INJ-COLLUSION-MARKET-001`), memory poisoning for coordinator (`INJ-MEMORY-POISON-COORD-001`), plus identity spoofing, replay, stealthy poisoning, slow-roll poisoning, and collusion.
- **Injection to sec.* and harness**: Each injection_id in the spec must have an entry in the risk injector registry (`INJECTION_REGISTRY` in `risk_injections.py`). The injector implements `get_metrics()` returning `attack_success`, `first_application_step`, `first_detection_step`, `first_containment_step`; `metrics.compute_episode_metrics` maps these to `sec.attack_success_rate`, `sec.detection_latency_steps`, `sec.containment_time_steps`, and optionally `sec.stealth_success_rate`, `sec.time_to_attribution_steps`, `sec.blast_radius_proxy`. Any new injection added to the spec must implement a harness and `get_metrics()` so that summary_coord.csv and results.json record sec.* consistently.
- **INJ-BID-SPOOF-001**: Currently mapped to the same harness as collusion (CollusionInjector), which covers bid/market manipulation. A dedicated BidSpoofInjector targeting the bid/proposal path may be added later if product/security requests a distinct bid-spoof scenario.
- **Metrics**: Per cell, `sec.attack_success_rate`, `sec.detection_latency_steps`, `sec.containment_time_steps`; optional `sec.stealth_success_rate`, `sec.time_to_attribution_steps`, `sec.blast_radius_proxy` support security evaluation. Success/detection/containment are defined per injection in the injections spec.
- **Method-risk matrix**: `policy/coordination/method_risk_matrix.v0.1.yaml` defines coverage (covered / partially_covered / uncovered) and `required_bench` per (method_id, risk_id). LLM methods (e.g. llm_constrained, llm_central_planner) have explicit risk rows for tool, prompt, and data risks.

## Reporting format

- **summary_coord.csv**: One row per cell (method_id, scale_id, risk_id, injection_id). Columns include:
  - Identifiers: `method_id`, `scale_id`, `risk_id`, `injection_id`
  - Performance: `perf.throughput`, `perf.p95_tat`
  - Safety: `safety.violations_total`, `safety.blocks_total`
  - Security: `sec.attack_success_rate`, `sec.detection_latency_steps`, `sec.containment_time_steps`, `sec.stealth_success_rate`, `sec.time_to_attribution_steps`, `sec.blast_radius_proxy`
  - Resilience: `robustness.resilience_score`, `resilience.component_perf`, `resilience.component_safety`, `resilience.component_security`, `resilience.component_coordination`
  - Comms: `comm.msg_count`, `comm.p95_latency_ms`, `comm.drop_rate`, `comm.partition_events`
  - LLM-specific: `proposal_valid_rate`, `blocked_rate`, `repair_rate`, `tokens_per_step`, `p95_llm_latency_ms`

- **Pareto report (pareto.md)**: Per-scale Pareto front on objectives: minimize `p95_tat`, minimize `violations_total`, maximize `robustness.resilience_score`. Top methods per scale and **robust winner** (highest mean resilience across cells). Optional PARETO/ folder with `pareto.json`, `pareto.md`, `frontier.svg` for multi-objective evaluation and CIs.

- **Security metrics**: Security columns in summary_coord.csv and optional security block in per-cell results.json support reviewing attack success, detection, and containment across the injection set.

## Prompt integrity

For any run that uses an LLM backend in coordination (llm_* methods), the following are recorded for reproducibility and verification:

- **prompt_template_id**: Stable id per method (e.g. `coordination_llm_central_planner_v0.1`).
- **prompt_sha256**: SHA-256 of the canonical prompt representation (template + bounded state slice + allowed_actions payload + policy slice). Same seed and policy yield the same hash.
- **allowed_actions_payload_sha256**: SHA-256 of the canonical allowed-actions JSON payload (from RBAC / policy). Changing the policy file or allowed actions changes this hash.
- **coordination_policy_fingerprint**: Fingerprint of `policy/coordination_identity_policy.v0.1.yaml` (same as verify-bundle). Any change to that file changes the fingerprint.

**Where stored**: (1) results.json optional metadata block (`metadata.prompt_template_id`, `metadata.prompt_sha256`, `metadata.allowed_actions_payload_sha256`, `metadata.coordination_policy_fingerprint`); (2) EvidenceBundle manifest when export-receipts is run from a directory that contains results.json (and optionally `prompt_fingerprint_inputs.v0.1.json`). The manifest schema allows additional optional fields; existing fields are unchanged.

**Canonical rendering**: Prompt hashing uses deterministic, bounded slices: sort keys, stable JSON formatting, no timestamps, caps on list lengths and string sizes so the digest does not depend on unbounded policy or state.

**Verify-bundle**: When `prompt_sha256` is present in the manifest, verify-bundle requires `prompt_fingerprint_inputs.v0.1.json` in the bundle. It recomputes the hash from the stored inputs (frozen template + rendered policy payload) and reports a mismatch if it does not equal the manifest value. This ensures the recorded prompt hash matches the deterministic rendering of the same inputs.

## External reviewer workflow (offline)

1. **Run coordination study (deterministic, no network)**  
   `labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out <dir> --llm-backend deterministic`  
   No API key or network required. On Windows, run the external reviewer script under WSL or ensure shell scripts use LF (e.g. `.gitattributes` sets `*.sh text eol=lf`). Same `seed_base` and spec yield reproducible `summary_coord.csv` and cell results.

   **Script**: `scripts/run_external_reviewer_checks.sh [out_dir] [spec_path]` runs the study, checks that `summary/summary_coord.csv` exists with required columns (method_id, scale_id, injection_id, sec.attack_success_rate, proposal_valid_rate), optionally runs `verify-bundle` on the first EvidenceBundle under the output dir, and ensures or generates `COORDINATION_LLM_CARD.md`. Exit 0 only if all checks pass. Optional CI job: set `LABTRUST_EXTERNAL_REVIEWER_CHECKS=1` (e.g. in schedule or workflow_dispatch with "Run external reviewer checks") to run this script in CI; the job uses the smoke spec for speed.

2. **Verify bundles**  
   After a run that produced receipts (e.g. package-release or a run with episode log and export-receipts), run `labtrust verify-bundle --bundle <path_to_EvidenceBundle.v0.1>` to validate integrity and policy alignment.

3. **Review coverage**  
   Check that the study spec includes the desired injections and methods; compare `summary_coord.csv` columns and method_risk_matrix required_bench cells to confirm risk coverage gates are met.

4. **Review COORDINATION_CARD and COORDINATION_LLM_CARD**  
   Package-release profile `paper_v0.1` produces `COORDINATION_CARD.md` (general coordination benchmark card) and `COORDINATION_LLM_CARD.md` (LLM-specific methods, backends, injection coverage, limitations). Use these for scope and reproducibility claims.

## Next steps of improvement

- **Live backends**: `llm_central_planner`, `llm_hierarchical_allocator`, and `llm_auction_bidder` support `openai_live` (OpenAI Responses API) and `ollama_live` (local Ollama when configured). Central planner and hierarchical allocator use CoordinationProposal (per_agent); auction bidder uses a bid backend (market[] bids). For ollama_live, set LABTRUST_LOCAL_LLM_URL and LABTRUST_LOCAL_LLM_MODEL.
- **Structured cost and latency in results**: Persist per-step LLM metadata (latency, tokens, cost) in episode logs and ensure they aggregate correctly in study summary when multiple cells use live backends.
- **Repair loop caps and policy**: Make `max_repairs` and `blocked_threshold` configurable via coordination policy or scale config so studies can compare different repair policies.
- **Security metrics coverage**: Ensure every injection in the study spec has a well-defined success/detection/containment outcome and that summary_coord.csv and results.json record them consistently; add any missing sec.* columns for new injection types.
- **Determinism and hashing**: Document and test that episode log hashes (and summary_coord.csv content hash) are stable for deterministic runs when LLM backend is deterministic; consider including proposal_hash and shield_outcome_hash in a compact audit digest for verification.
- **External reviewer automation**: Provide a small script or CI job that runs `run-coordination-study --llm-backend deterministic`, then `verify-bundle` on a chosen receipt, and checks that COORDINATION_LLM_CARD.md and coverage gates are present in the artifact.
