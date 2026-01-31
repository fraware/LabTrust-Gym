# LLM agent baselines

Offline-safe, deterministic-by-default LLM agent interface for LabTrust-Gym.

## Design

- **LLMBackend protocol**: `generate(messages) -> text`. Backends are pluggable.
- **LLMAgent**: Builds a system prompt (allowed actions, constraints), calls the backend, parses output as **strict JSON** (action_type + action_info), and validates against `policy/llm/action_schema.v0.1.json`. On parse or validation failure, returns NOOP.
- **Deterministic by default**: Use `MockDeterministicBackend` for tests and demos; no API calls. Real providers are optional and never used in default tests.

## Action schema

- **policy/llm/action_schema.v0.1.json**: JSON Schema for LLM-proposed actions.
  - **action_type**: integer 0–5 (0=NOOP, 1=TICK, 2=QUEUE_RUN, 3=MOVE, 4=OPEN_DOOR, 5=START_RUN).
  - **action_info**: optional object with device_id, work_id, priority, to_zone, door_id, token_refs.
- Proposed action JSON is validated before use; invalid output is rejected (agent falls back to NOOP).

## Backends

### MockDeterministicBackend

- **Offline-safe**: No network; returns canned JSON keyed by hash of the user message (e.g. observation hash).
- **Deterministic**: Same message → same response. Use for tests and demos.
- Constructor: `MockDeterministicBackend(canned=None, default_action_type=0)`. `canned` is a dict mapping `hash(user_content)[:16]` → action dict.

### OpenAIBackend (stub)

- Reads API key from env var `OPENAI_API_KEY`.
- **Stub**: Does not call the API; returns NOOP if no key, else raises NotImplementedError. Not used in tests. Plug a real implementation when needed.

## Safe usage

1. **Tests and CI**: Use only `MockDeterministicBackend`. No API keys; no network.
2. **Real providers**: Implement `LLMBackend` (e.g. OpenAI, local model). Keep API keys in env vars; do not commit.
3. **Strict output**: LLMAgent expects a single JSON object. Wrap model output (e.g. strip markdown, extract JSON) before parse. Invalid JSON or schema failure → NOOP.
4. **Constraints in prompt**: System prompt describes allowed action_type values and constraints (e.g. no restricted door without token). The environment still enforces; the LLM only proposes.

## Example

```bash
python examples/llm_agent_mock_demo.py
```

Runs TaskB with `LLMAgent(MockDeterministicBackend())` as ops_0 and scripted runners. No API calls.

## Tests

- **tests/test_llm_agent_mock.py**: Mock backend determinism, LLMAgent parse/validate, action schema validation. No real LLM calls; golden suite unchanged.
