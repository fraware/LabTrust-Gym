# LLM agent baselines

Offline-safe, **constrained and reproducible by default** LLM agent interface for LabTrust-Gym.

## Design

- **LLMBackend protocol**: `generate(messages) -> text`. Backends are pluggable.
- **LLMAgent**: Builds a system prompt (allowed actions, constraints), calls the backend, parses output as **strict JSON** (action_type + action_info), and validates against `policy/llm/action_schema.v0.1.json`. On parse or validation failure, returns NOOP.
- **LLMAgentWithShield (v1)**: Uses **llm_action.schema.v0.2** (string action_type). Proposes action from backend, then **constrained decode** (schema + rationale + allowed_actions at decode time) and **safety shield** (RBAC + signature). Returns `(action_index, action_info, meta)`; when blocked, `meta` has `_shield_filtered` and `_shield_reason_code`, and the step output records **LLM_ACTION_FILTERED** in emits. **Rationale is required** (explainable actions).
- **Deterministic by default**: **pipeline_mode=deterministic** uses **FixtureBackend** (offline lookup from `tests/fixtures/llm_responses/`). Alternatively use **DeterministicConstrainedBackend(seed)** via `--llm-backend deterministic_constrained` (seeded RNG, no fixtures). Online mode can opt into **OpenAIHostedBackend** (api.openai.com only, `OPENAI_API_KEY`). Deterministic CI never performs network calls.

## Action schema

- **policy/llm/action_schema.v0.1.json**: JSON Schema for LLM-proposed actions (integer action_type).
  - **action_type**: integer 0–5 (0=NOOP, 1=TICK, 2=QUEUE_RUN, 3=MOVE, 4=OPEN_DOOR, 5=START_RUN).
  - **action_info**: optional object with device_id, work_id, priority, to_zone, door_id, token_refs.
- **policy/llm/llm_action.schema.v0.2.json**: Structured action candidate for shield (string action_type).
  - **action_type**: string (NOOP, TICK, MOVE, QUEUE_RUN, START_RUN, RELEASE_RESULT, etc.).
  - **args**, **key_id**, **signature**, **token_refs**, **reason_code**, **rationale** (required for constrained baseline: explainable).
- **policy/llm/policy_summary.schema.v0.1.json**: What the agent can see (allowed_actions, zone_graph, queue_head, pending_criticals, key_constraints, critical_ladder_summary, restricted_zones, token_requirements, log_frozen, strict_signatures). Use **generate_policy_summary_from_policy(repo_root, ...)** to build from policy files.
- **Canonical allowed-actions payload**: `src/labtrust_gym/baselines/llm/allowed_actions_payload.py` defines **ACTION_SPEC_REGISTRY** and **build_allowed_actions_payload()**. The payload includes per-action `action_type`, `args_examples`, `required_tokens`, and `description`, and is capped in size. Both **DeterministicConstrainedBackend** and **OpenAILiveBackend** inject this payload into the user prompt so the LLM sees a single, consistent action spec.
- Proposed action JSON is validated (schema + rationale + allowed_actions) at **decode time**; invalid or RBAC-inconsistent output is rejected (NOOP with reason_code) before env step.

## LLM audit events

When the LLM agent proposes an action, the engine records an audit event:

- **Emit type**: **LLM_DECISION** (in `policy/emits/emits_vocab.v0.1.yaml`).
- **Audit payload** (`_llm_decision`): Written to the episode log and to evidence bundles. Fields: `backend_id`, `model_id`, `prompt_sha256`, `response_sha256`, `latency_ms`, `action_proposal` (the proposed action dict or null on error), `error_code` (e.g. parse/shield reason or `n/a`), `used_structured_outputs` (bool). When applicable: **`agent_id`**, **`role_id`** (for role-aware prompts); **`signed_by_proxy`**, **`key_id_used`** (when signing proxy is used); **`prompt_tokens`**, **`completion_tokens`**, **`total_tokens`** (when the backend reports usage).

This supports forensics and reproducibility checks (e.g. hashing prompt/response, latency, token usage, and whether structured outputs were used).

## Role-aware prompts and per-agent routing

- **Prompt registry** (`policy/llm/prompt_registry.v0.1.yaml`): System prompt templates per role (e.g. `ops_reception_v2`, `ops_analytics_v2`, `ops_transport_v2`).
- **Role-to-prompt mapping** (`policy/llm/role_to_prompt.v0.1.yaml`): Maps `role_id` to prompt ID. `get_prompt_id_for_role(role_id, repo_root)` in `src/labtrust_gym/policy/prompt_registry.py` selects the template.
- **LLMAgentWithShield** uses the agent's `role_id` (from the environment) to choose the system prompt; audit payload includes **agent_id** and **role_id**.
- **CLI**: `run-benchmark --llm-agents <agent_ids>` restricts which agents use the LLM (default: all ops agents when `--llm-backend` is set).

## Signing proxy (strict_signatures)

When the engine runs with **strict_signatures**, mutating actions must be signed. For the LLM agent:

- **Signing proxy** (`src/labtrust_gym/baselines/llm/signing_proxy.py`): Selects a key from the key registry (by agent_id/role_id), signs the event payload (with `last_event_hash`), and attaches `key_id` and `signature` to the action before the safety shield. Supports **ephemeral key** generation for runs (e.g. when no key is bound to the agent).
- The benchmark runner loads the key registry and configures the proxy for LLMAgentWithShield; insider_key_misuse and shift-change scenarios use strict_signatures with the proxy.
- Audit: **signed_by_proxy** (bool) and **key_id_used** in LLM_DECISION.

## Provider-neutral live interface

- **ProviderBackend** (protocol in `baselines.llm.provider`): live backends return **ActionProposal** dicts via `propose_action(context)`. No optional deps; engine logic depends only on this interface.
- **Capability flags**: `supports_structured_outputs` (bool), `supports_tool_calls` (bool). Backends set them; best quality when structured outputs are supported (e.g. OpenAI with `response_format`).
- **Per-provider code** is behind optional extras: **llm_openai** (OpenAILiveBackend), **llm_anthropic** (later). **OllamaLiveBackend** (no extra) for local Ollama. Add new providers without touching engine logic.
- **Fallback path**: If a provider does not support strict JSON schema, the agent uses **parse_utils.extract_first_json_object** to extract a JSON object from raw text, then validate + NOOP on failure. Audit field **used_structured_outputs** in LLM_DECISION records whether the backend natively returned schema-conforming output (preferred) or fallback was used.

## Backends

### MockDeterministicBackend

- **Offline-safe**: No network; returns canned JSON keyed by hash of the user message (e.g. observation hash).
- **Deterministic**: Same message → same response. Use for tests and demos.
- Constructor: `MockDeterministicBackend(canned=None, default_action_type=0)`. `canned` is a dict mapping `hash(user_content)[:16]` → action dict.

### MockDeterministicBackendV2

- Returns **llm_action.schema.v0.2** format (string **action_type**, **args**, **rationale**, etc.).
- **canned**: hash of user message (JSON with `obs_hash`, `allowed_actions`) → action dict. **default_action_type**: string (e.g. `"NOOP"`).
- Use with **LLMAgentWithShield** for tests that supply canned actions (must include **rationale**).

### FixtureBackend (deterministic, default for pipeline_mode=deterministic)

- **Offline-only**: Looks up response by digest of messages in `tests/fixtures/llm_responses/fixtures.json`. No network.
- Key is SHA-256 of canonical JSON messages. If no fixture exists for a request, raises **FixtureMissingError** with remediation to run **record-llm-fixtures** (with network) to record fixtures.
- Enable via CLI: `labtrust run-benchmark --llm-backend deterministic`. Requires fixtures to have been recorded first, or use `--llm-backend deterministic_constrained` for seeded RNG without fixtures.

### DeterministicConstrainedBackend (seeded RNG, no fixtures)

- Chooses from **allowed_actions** using a **seeded RNG** (no API calls, no fixture files).
- Constructor: `DeterministicConstrainedBackend(seed, default_action_type="NOOP")`. User message must be JSON with `allowed_actions` (list of action_type strings).
- Same **seed** + same call order ⇒ same action sequence. Enable via CLI: `labtrust run-benchmark --llm-backend deterministic_constrained` (default when `--use-llm-safe-v1-ops` is used).
- Always returns **rationale**: `"deterministic baseline"`.

### OpenAIHostedBackend (OpenAI-hosted only)

- **Real backend**: Uses official OpenAI SDK with `api_key` from env **OPENAI_API_KEY** only. No base_url or gateway; api.openai.com only.
- Strict timeouts and bounded retries. Raises **AuthError** if `OPENAI_API_KEY` is missing (no network call), **RateLimitError** (429), **ProviderUnavailable** (timeout/5xx).
- Implements **LLMBackend** (`generate(messages) -> str`). Optional extra: `.[llm_openai]`. Enable via CLI: `labtrust run-benchmark --llm-backend openai_hosted --allow-network`.

### OpenAILiveBackend (live provider)

- **ProviderBackend** implementation: calls OpenAI Chat Completions with Structured Outputs (optional; falls back to parse if unsupported). Requires `OPENAI_API_KEY` and optional `.[llm_openai]` extra.
- Uses the **canonical allowed-actions payload** from `allowed_actions_payload.py` in the user prompt. Exposes **get_aggregate_metrics()** (total calls, error count, sum latency ms, **prompt_tokens**, **completion_tokens**, **total_tokens**, **p50/p95 latency**) for results metadata; cost estimated from **policy/llm/model_pricing.v0.1.yaml** when the model is listed.
- Enable via CLI: `labtrust run-benchmark --llm-backend openai_live`. Non-deterministic; incurs API cost. See [Live LLM benchmark mode](llm_live.md).

### OllamaLiveBackend (local Ollama)

- **ProviderBackend** implementation for local Ollama (no optional extra). Configure via environment: **LABTRUST_LOCAL_LLM_URL** (e.g. `http://localhost:11434`), **LABTRUST_LOCAL_LLM_MODEL** (e.g. `llama3.2`), **LABTRUST_LOCAL_LLM_TIMEOUT** (seconds).
- Sets **supports_structured_outputs = False**; the agent uses **parse_utils.extract_first_json_object** to extract JSON from the raw response.
- Enable via CLI: `labtrust run-benchmark --llm-backend ollama_live`. Non-deterministic; no API cost if running locally.

## Constrained decoder + safety shield (v1)

- **Constrained decoder** (`src/labtrust_gym/baselines/llm/decoder.py`): At **decode time** (before env step), validates schema, **requires rationale**, restricts **action_type** to `allowed_actions`, and optionally checks zone/device. Refuses impossible actions (RBAC/devices/zones) so the agent cannot propose them without being rejected at decode time.
- **Shield** (`src/labtrust_gym/baselines/llm/shield.py`): After decode, filters through **RBAC** (context) and **signature required** (when `strict_signatures`). Token validity is left to the engine.
- If blocked (decode or shield): returns safe NOOP, `_shield_filtered=True`, and **reason_code** (e.g. `MISSING_RATIONALE`, `RBAC_ACTION_DENY`, `SIG_MISSING`). Step output records **LLM_ACTION_FILTERED** in emits and `blocked_reason_code`.
- **multi_site_stat and insider_key_misuse** run with **llm_safe_v1** deterministically: `run_benchmark(..., use_llm_safe_v1_ops=True)` uses `--llm-backend deterministic_constrained` by default (seeded RNG). Use `--llm-backend deterministic` for FixtureBackend (requires recorded fixtures). insider_key_misuse demonstrates signature/RBAC attack containment with the LLM baseline.

## Deterministic vs non-deterministic

- **Deterministic**: **FixtureBackend** (offline lookup from fixtures; run **record-llm-fixtures** with network to populate) or **DeterministicConstrainedBackend(seed)** / **MockDeterministicBackendV2(canned=...)**. Same inputs ⇒ same actions. Required for CI; deterministic CI never performs network calls.
- **Non-deterministic**: **OpenAIHostedBackend**, **OpenAILiveBackend**, or local Ollama. Use `--llm-backend openai_hosted` or `openai_live` with `--allow-network` for live runs. Do not compare metrics across runs without fixing seed/temperature on the provider side.

## Recording fixtures (offline-friendly design)

- **record-llm-fixtures**: CLI command to populate `tests/fixtures/llm_responses/` from OpenAI responses. Run **manually** with network enabled (not in CI): `labtrust record-llm-fixtures --task insider_key_misuse --episodes 1`. Requires `OPENAI_API_KEY`. After recording, deterministic runs with `--llm-backend deterministic` use these fixtures and do not call the network.

## Safe usage

1. **Tests and CI**: Use **FixtureBackend** (with pre-recorded fixtures), **DeterministicConstrainedBackend**, or **MockDeterministicBackend** / **MockDeterministicBackendV2**. No API keys; no network in deterministic pipeline.
2. **Real providers**: Use **OpenAIHostedBackend** (`--llm-backend openai_hosted`) or **OpenAILiveBackend** (`--llm-backend openai_live`) with `--allow-network` only when needed.
3. **Strict output**: LLMAgent expects a single JSON object. Wrap model output (e.g. strip markdown, extract JSON) before parse. Invalid JSON or schema failure → NOOP. **Rationale** is required for the constrained path.
4. **Constraints in prompt**: System prompt describes allowed action_type values and constraints. The **decoder** refuses actions not in `allowed_actions` at decode time; the environment still enforces the rest.

## Example

```bash
python examples/llm_agent_mock_demo.py
```

Runs stat_insertion with `LLMAgent(MockDeterministicBackend())` as ops_0 and scripted runners. No API calls.

## Prompt-injection golden scenarios

- **policy/golden/prompt_injection_scenarios.v0.1.yaml** defines adversarial strings injected into specimen notes and transport/scenario notes. The LLM agent receives observations containing these strings.
- **tests/test_llm_prompt_injection_golden.py**: Runs LLMAgentWithShield (deterministic and optionally openai_live) against observations with injected adversarial content; asserts that the **proposed** `action_type` (from `_llm_decision.action_proposal`) is always in `allowed_actions` or NOOP, and that blocked-count deltas stay within a threshold. See [Frozen contracts](frozen_contracts.md) for the contract on these scenarios.

## Token usage and cost accounting

- **OpenAILiveBackend** captures **prompt_tokens**, **completion_tokens**, **total_tokens** from the API and aggregates them; **get_aggregate_metrics()** also returns latency percentiles (p50, p95).
- **policy/llm/model_pricing.v0.1.yaml** lists per-1M-token input/output prices (USD) for models; the runner computes **estimated_cost_usd** when the model is listed.
- Results **metadata** (and package-release **TABLES/llm_economics.csv**, **llm_economics.md**) include total_tokens, tokens_per_step, estimated_cost_usd, and latency percentiles when an LLM backend was used. See [Live LLM benchmark mode](llm_live.md#cost-accounting).

## Tests

- **tests/test_llm_agent_mock.py**: Mock backend determinism, LLMAgent parse/validate, action schema validation. **LLM v1 + shield**: MockDeterministicBackendV2 determinism, llm_action.v0.2 schema validation, **shield determinism** (same obs → same (idx, info, meta)), **safety** (forbidden action e.g. RELEASE_RESULT for A_RECEPTION → shield blocks with RBAC_ACTION_DENY), **multi_site_stat/insider_key_misuse with use_llm_safe_v1_ops** (deterministic metrics). No real LLM calls; golden suite unchanged.
- **tests/test_llm_constrained_decoder.py**: **Constrained decoder**: illegal action (not in allowed_actions) → rejected, NOOP, RBAC_ACTION_DENY; missing rationale → rejected, NOOP, MISSING_RATIONALE; valid action with rationale → pass. **DeterministicConstrainedBackend**: same seed ⇒ same action sequence; fixed seed reproducible. **insider_key_misuse** with LLM baseline: RBAC/insider containment demonstrated.
- **tests/test_signing_proxy.py**: Key selection, sign_event_payload, ephemeral key, ensure_run_ephemeral_key.
- **tests/test_prompt_registry.py**: get_prompt_id_for_role, role-to-prompt mapping, shift-change scenario.
- **tests/test_parse_utils.py**: extract_first_json_object for robust JSON extraction.
- **tests/test_ollama_live.py**: OllamaLiveBackend configuration and error handling.
- **tests/test_llm_prompt_injection_golden.py**: Prompt-injection golden scenarios (see above).
