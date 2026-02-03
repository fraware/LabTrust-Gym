# LLM agent baselines

Offline-safe, **constrained and reproducible by default** LLM agent interface for LabTrust-Gym.

## Design

- **LLMBackend protocol**: `generate(messages) -> text`. Backends are pluggable.
- **LLMAgent**: Builds a system prompt (allowed actions, constraints), calls the backend, parses output as **strict JSON** (action_type + action_info), and validates against `policy/llm/action_schema.v0.1.json`. On parse or validation failure, returns NOOP.
- **LLMAgentWithShield (v1)**: Uses **llm_action.schema.v0.2** (string action_type). Proposes action from backend, then **constrained decode** (schema + rationale + allowed_actions at decode time) and **safety shield** (RBAC + signature). Returns `(action_index, action_info, meta)`; when blocked, `meta` has `_shield_filtered` and `_shield_reason_code`, and the step output records **LLM_ACTION_FILTERED** in emits. **Rationale is required** (explainable actions).
- **Deterministic by default**: Use **DeterministicConstrainedBackend(seed)** as the official LLM baseline; it chooses from `allowed_actions` with a seeded RNG. Same seed ⇒ same action sequence. Real providers are optional and never used in default tests.

## Action schema

- **policy/llm/action_schema.v0.1.json**: JSON Schema for LLM-proposed actions (integer action_type).
  - **action_type**: integer 0–5 (0=NOOP, 1=TICK, 2=QUEUE_RUN, 3=MOVE, 4=OPEN_DOOR, 5=START_RUN).
  - **action_info**: optional object with device_id, work_id, priority, to_zone, door_id, token_refs.
- **policy/llm/llm_action.schema.v0.2.json**: Structured action candidate for shield (string action_type).
  - **action_type**: string (NOOP, TICK, MOVE, QUEUE_RUN, START_RUN, RELEASE_RESULT, etc.).
  - **args**, **key_id**, **signature**, **token_refs**, **reason_code**, **rationale** (required for constrained baseline: explainable).
- **policy/llm/policy_summary.schema.v0.1.json**: What the agent can see (allowed_actions, zone_graph, queue_head, pending_criticals, key_constraints, critical_ladder_summary, restricted_zones, token_requirements, log_frozen, strict_signatures). Use **generate_policy_summary_from_policy(repo_root, ...)** to build from policy files.
- Proposed action JSON is validated (schema + rationale + allowed_actions) at **decode time**; invalid or RBAC-inconsistent output is rejected (NOOP with reason_code) before env step.

## Provider-neutral live interface

- **ProviderBackend** (protocol in `baselines.llm.provider`): live backends return **ActionProposal** dicts via `propose_action(context)`. No optional deps; engine logic depends only on this interface.
- **Capability flags**: `supports_structured_outputs` (bool), `supports_tool_calls` (bool). Backends set them; best quality when structured outputs are supported (e.g. OpenAI with `response_format`).
- **Per-provider code** is behind optional extras: **llm_openai** (OpenAILiveBackend), **llm_anthropic** (later). Add new providers without touching engine logic.
- **Fallback path**: If a provider does not support strict JSON schema, the agent still runs: it calls `generate(messages) -> str`, then **parse + validate + NOOP on failure**. Audit field **used_structured_outputs** in LLM_DECISION records whether the backend natively returned schema-conforming output (preferred) or fallback was used.

## Backends

### MockDeterministicBackend

- **Offline-safe**: No network; returns canned JSON keyed by hash of the user message (e.g. observation hash).
- **Deterministic**: Same message → same response. Use for tests and demos.
- Constructor: `MockDeterministicBackend(canned=None, default_action_type=0)`. `canned` is a dict mapping `hash(user_content)[:16]` → action dict.

### MockDeterministicBackendV2

- Returns **llm_action.schema.v0.2** format (string **action_type**, **args**, **rationale**, etc.).
- **canned**: hash of user message (JSON with `obs_hash`, `allowed_actions`) → action dict. **default_action_type**: string (e.g. `"NOOP"`).
- Use with **LLMAgentWithShield** for tests that supply canned actions (must include **rationale**).

### DeterministicConstrainedBackend (official LLM baseline)

- **Constrained and reproducible by default.** Chooses from **allowed_actions** using a **seeded RNG** (no API calls).
- Constructor: `DeterministicConstrainedBackend(seed, default_action_type="NOOP")`. User message must be JSON with `allowed_actions` (list of action_type strings).
- Same **seed** + same call order ⇒ same action sequence. Used by `run_benchmark(..., use_llm_safe_v1_ops=True)` for TaskE/TaskF.
- Always returns **rationale**: `"deterministic baseline"`.

### OpenAIBackend (stub)

- Reads API key from env var `OPENAI_API_KEY`.
- **Stub**: Does not call the API; returns NOOP if no key, else raises NotImplementedError. Not used in tests. Plug a real implementation when needed.

## Constrained decoder + safety shield (v1)

- **Constrained decoder** (`src/labtrust_gym/baselines/llm/decoder.py`): At **decode time** (before env step), validates schema, **requires rationale**, restricts **action_type** to `allowed_actions`, and optionally checks zone/device. Refuses impossible actions (RBAC/devices/zones) so the agent cannot propose them without being rejected at decode time.
- **Shield** (`src/labtrust_gym/baselines/llm/shield.py`): After decode, filters through **RBAC** (context) and **signature required** (when `strict_signatures`). Token validity is left to the engine.
- If blocked (decode or shield): returns safe NOOP, `_shield_filtered=True`, and **reason_code** (e.g. `MISSING_RATIONALE`, `RBAC_ACTION_DENY`, `SIG_MISSING`). Step output records **LLM_ACTION_FILTERED** in emits and `blocked_reason_code`.
- **TaskE and TaskF** run with **llm_safe_v1** deterministically: `run_benchmark(..., use_llm_safe_v1_ops=True)` uses `LLMAgentWithShield(DeterministicConstrainedBackend(seed=base_seed), rbac_policy, pz_to_engine)` for ops_0. TaskF demonstrates signature/RBAC attack containment with the LLM baseline.

## Deterministic vs non-deterministic

- **Deterministic (default)**: `DeterministicConstrainedBackend(seed)` or `MockDeterministicBackendV2(canned=...)` with fixed inputs. Same seed / same canned keys ⇒ same actions. Required for CI, benchmarks, and reproducibility.
- **Non-deterministic**: Real LLM provider (e.g. OpenAI, local model). Use behind a **flag** (e.g. `use_real_llm=True`) so that:
  - Default runs (tests, `run_benchmark`, studies) use the deterministic backend and remain reproducible.
  - Optional runs with the flag call the real API; do not compare metrics across runs without fixing seed/temperature on the provider side.

## Plugging a real provider without breaking reproducibility

1. Implement `LLMBackend` (e.g. `OpenAIBackend` or a wrapper that calls your API). Keep API keys in env vars; do not commit.
2. Do **not** wire the real backend into `run_benchmark` or CI by default. Keep `use_llm_safe_v1_ops=True` using `DeterministicConstrainedBackend(seed)` so that benchmarks and TaskF remain reproducible.
3. For experiments with a real LLM, instantiate `LLMAgentWithShield(backend=YourRealBackend(), ...)` in a separate script or behind a CLI flag (e.g. `--llm-provider openai`). The constrained decoder and shield still apply; only the action proposal is non-deterministic.

## Safe usage

1. **Tests and CI**: Use only `DeterministicConstrainedBackend` or `MockDeterministicBackend` / `MockDeterministicBackendV2`. No API keys; no network.
2. **Real providers**: Implement `LLMBackend`; use behind a flag so default behaviour stays reproducible.
3. **Strict output**: LLMAgent expects a single JSON object. Wrap model output (e.g. strip markdown, extract JSON) before parse. Invalid JSON or schema failure → NOOP. **Rationale** is required for the constrained path.
4. **Constraints in prompt**: System prompt describes allowed action_type values and constraints. The **decoder** refuses actions not in `allowed_actions` at decode time; the environment still enforces the rest.

## Example

```bash
python examples/llm_agent_mock_demo.py
```

Runs TaskB with `LLMAgent(MockDeterministicBackend())` as ops_0 and scripted runners. No API calls.

## Tests

- **tests/test_llm_agent_mock.py**: Mock backend determinism, LLMAgent parse/validate, action schema validation. **LLM v1 + shield**: MockDeterministicBackendV2 determinism, llm_action.v0.2 schema validation, **shield determinism** (same obs → same (idx, info, meta)), **safety** (forbidden action e.g. RELEASE_RESULT for A_RECEPTION → shield blocks with RBAC_ACTION_DENY), **TaskE/TaskF with use_llm_safe_v1_ops** (deterministic metrics). No real LLM calls; golden suite unchanged.
- **tests/test_llm_constrained_decoder.py**: **Constrained decoder**: illegal action (not in allowed_actions) → rejected, NOOP, RBAC_ACTION_DENY; missing rationale → rejected, NOOP, MISSING_RATIONALE; valid action with rationale → pass. **DeterministicConstrainedBackend**: same seed ⇒ same action sequence; fixed seed reproducible. **TaskF** with LLM baseline: RBAC/insider containment demonstrated.
