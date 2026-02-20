# Testing strategy

LabTrust-Gym uses deterministic unit and integration tests, a **fuzz harness** for contract and safety checks, and **metamorphic testing** to prove robustness without relying on hand-written oracles alone.

## Fuzz harness

**Location:** `src/labtrust_gym/testing/fuzz.py`

The fuzzer generates **random but valid** event sequences constrained by:

- **Policy schemas:** `labtrust validate-policy` validates all policy YAML/JSON under `policy/`; the fuzzer uses the same policy root so generated events are consistent with loaded RBAC, zones, and tool registry.
- **Tool arg schemas:** For tool calls (`tool_id` set), arguments are generated from `policy/tool_args/*.schema.json` so that required fields and types (string, integer, min/max) are satisfied. This avoids trivial TOOL_ARG_SCHEMA_FAIL/TOOL_ARG_RANGE_FAIL and focuses on deeper contract and safety issues.

Behavior:

- **Deterministic given seed:** Same seed produces the same event sequence and same env behavior when `deterministic=True` and `rng_seed` are fixed.
- **Checks:** Contract (every step has `status`, `emits`, `violations`; `status` in `ACCEPTED`|`BLOCKED`), non-determinism (run same sequence twice, compare canonical step results).
- **Reproducers:** When a counterexample is found (contract violation or non-determinism), a minimal reproducer YAML is written to **`runs/fuzz_failures/`** with:
  - `seed`, `failure_type`, `message`
  - `initial_state`, `events`

Filename pattern: `fuzz_<failure_type>_seed<seed>.yaml`. These can be replayed or added to the test suite.

Usage (e.g. in a test or script):

```python
from labtrust_gym.testing.fuzz import run_fuzz_session, generate_event_sequence

# Generate one sequence (e.g. for custom tests)
events = generate_event_sequence(seed=42, policy_root=Path("."), max_steps=10)

# Run a short fuzz session with env
passed, failures = run_fuzz_session(
    seed=42,
    initial_state_factory=lambda: minimal_initial_state(...),
    env_factory=lambda: CoreEnv(),
    policy_root=Path("."),
    max_steps=15,
    max_sequences=5,
    check_determinism=True,
    out_dir=Path("runs/fuzz_failures"),
)
assert passed, failures
```

The harness is intended for CI smoke (with a fixed seed and small `max_sequences`) or for longer runs when investigating regressions.

## Metamorphic testing

**Location:** `tests/test_metamorphic_properties.py`

Metamorphic relations are properties of the form: *if we transform the input in a defined way, some relation must hold on the outputs.* They do not require a single “correct” output; they only require consistency across the transformation.

All tests are **seeded** (e.g. `SEED = 42`) so results are reproducible in CI.

Defined relations (5–10 properties):

1. **Determinism (same seed, same outcomes):** Running the same event sequence twice with the same seed yields identical step results.
2. **Renaming agent IDs preserves safety outcome:** Applying a bijection on `agent_id` (e.g. swapping two agents in the roster and in events) does not change the accept/block pattern for role-permitted actions (e.g. TICK).
3. **Reordering irrelevant events does not create a release:** Reordering two TICK events does not introduce a RELEASE that was not present in the original order.
4. **Doubling tick timesteps:** Doubling `t_s` for a TICK-only sequence does not change accept/block outcomes.
5. **Append no-op TICK:** Adding a no-op TICK at the end does not change prior step outcomes.
6. **Empty sequence, no releases:** An empty event sequence yields no releases (trivial; reinforces contract).
7. **Same event twice, same result:** Repeating the same event twice with the same seed gives the same result for both steps (determinism per event type).
8. **Different seed, contract still holds:** Different seeds may yield different outcomes; every step result still has `status` in `ACCEPTED`|`BLOCKED` and `emits` as a list.
9. **Contract required keys:** Every step result contains `status`, `emits`, and `violations`.

These are run in CI as part of the main test job (see below). Marked with `@pytest.mark.metamorphic` for optional filtering.

## Full test suite

Running **`pytest -v`** from the repo root executes all tests, including PettingZoo env smoke (`test_pz_parallel_smoke`, `test_pz_aec_smoke`), benchmark smoke (`test_benchmark_smoke`), CLI smoke matrix, coordination conformance (`tests/coord_methods/conformance/test_conformance_contract_matrix.py`), and strictly-better scenario tests (`tests/test_coord_strictly_better.py`). Expected result: **all tests pass** (extensive suite), with a number of tests skipped (e.g. MARL smoke when `LABTRUST_MARL_SMOKE` is unset, golden suite when `LABTRUST_RUN_GOLDEN` is unset, live-LLM or missing backends), in about 10 minutes. Default run uses `--timeout=120` per test (see `pyproject.toml`). Markers: **slow** (golden suite, package-release, heavy CLI; exclude with `-m 'not slow'`), **metamorphic**, **determinism**, **live** (require OPENAI_API_KEY, LABTRUST_RUN_LLM_LIVE=1), **security** (fuzz and property tests). Skipped tests are intentional (optional MARL smoke, golden when `LABTRUST_RUN_GOLDEN` unset, live-LLM or missing backends). For a faster run, use `pytest -q` with optional `--ignore=tests/test_pz_parallel_smoke.py --ignore=tests/test_pz_aec_smoke.py --ignore=tests/test_benchmark_smoke.py` to exclude the heaviest smoke tests.

## Live LLM integration

The most important check that the live OpenAI path works end-to-end is **`test_openai_live_one_episode_task_a`** (marked `@pytest.mark.live`). It runs one benchmark episode with the real API and verifies the runner and backend integrate correctly. It is **skipped by default** so that normal CI and local `pytest` runs do not call the API or require a key.

To run it (recommended before releases or after LLM pipeline changes):

1. Set **`OPENAI_API_KEY`** to your key and **`LABTRUST_RUN_LLM_LIVE=1`**.
2. Run either:
   - **Script (PowerShell):** `.\scripts\run_live_llm_integration.ps1` (or `$env:OPENAI_API_KEY = "sk-..."; .\scripts\run_live_llm_integration.ps1`).
   - **pytest:** `pytest tests/test_openai_live.py::test_openai_live_one_episode_task_a -v` with the same env vars set.
   - **All live tests:** `pytest tests/test_openai_live.py -m live -v`.

On Windows PowerShell: `$env:OPENAI_API_KEY = "sk-..."; $env:LABTRUST_RUN_LLM_LIVE = "1"; pytest tests/test_openai_live.py::test_openai_live_one_episode_task_a -v`.

## Security fuzz and property tests (p8)

**Location:** `tests/test_security_property_fuzz.py`

Property-based and fuzzing tests for the security suite (injection points, no action outside allowed). Requires **hypothesis** (dev dependency: `pip install -e ".[dev]"`).

- **Property (no action outside allowed):** For any `allowed_actions` and any (possibly adversarial) observation text in injection fields, the shield output `action_type` and the raw proposal `action_type` must be in `allowed_actions` or NOOP.
- **Injection keys covered:** `specimen_note`, `scenario_note`, `transport_manifest_note` (aligned with `policy/golden/prompt_injection_scenarios.v0.1.yaml` and `security_runner`).
- **Suite-path fuzz:** Same property is checked via `security_runner._run_prompt_injection_attack` with hypothesis-generated adversarial strings, so the same code path as `run_security_suite` is fuzzed.

Run with: `pytest tests/test_security_property_fuzz.py -v` (or `-m security` to run only security-marked tests). If hypothesis is not installed, the three tests are skipped.

**p8 roadmap (step by step):** (1) Fuzzing on injection points with Hypothesis [done]; (2) Property-based regression and security suite gate [done]; (3) Red-team LLM strategies and regression suite [done]; (4) Invariants DSL and optional model checking [done].

**Step 4 (invariants DSL and model checking):**

- **Invariant spec schema:** `policy/schemas/invariant_spec.v0.1.schema.json` defines the declarative format for a single invariant (invariant_id, logic_template with type and parameters.check, severity, scope, etc.). Registry entries in `policy/invariants/invariant_registry.v1.0*.yaml` conform to this; new invariants can be validated against the schema before adding to the registry.
- **Bounded trace invariant checker:** `src/labtrust_gym/engine/model_checking.py` provides `check_critical_path_safety(event_trace, invariant_ids, max_steps, output_dir)` returning (safe, trace, violations). It evaluates invariants over recorded event traces (event+result per step), loads definitions from the policy invariant registry, and emits model_check_report.json and model_check_report.md when output_dir is set. Violations include invariant_id, step_index, evidence pointers, and a human-readable message.

**Step 3 (red-team LLM strategies and regression):**

- **Multiple strategies per attack:** The security runner supports optional `attacker_prompt_template_ids` (list) on an LLM-attacker attack; when set, the attack runs once per template and passes only if all pass. Single `attacker_prompt_template_id` remains supported.
- **New strategy prompt:** `policy/golden/llm_attacker_prompts.v0.1.yaml` includes `ATTACKER-IGNORE-INSTRUCTIONS` (strategy_id: ignore_instructions). New attack **SEC-LLM-ATTACK-004** uses it.
- **Red-team regression test** (`tests/test_security_attack_suite.py::test_red_team_llm_attacker_regression`): Runs the full suite with `llm_attacker=True`, `allow_network=True`; asserts every LLM-attacker attack passes (blocked). Skipped unless `LABTRUST_RUN_LLM_ATTACKER=1` and `OPENAI_API_KEY` are set. Marked `@pytest.mark.security` and `@pytest.mark.live`.

**Step 2 (regression gate):**

- **Security suite smoke gate** (`tests/test_security_attack_suite.py::test_security_suite_smoke_gate_all_passed`): Runs `run_security_suite(smoke_only=True, seed=42)` and asserts every attack passes. Fails the build if any prompt-injection or test_ref attack in the smoke set does not meet its expected outcome. Marked `@pytest.mark.security`; timeout 120s per test_ref.
- **Property regression set** (`tests/test_security_property_fuzz.py::test_property_no_action_outside_allowed_regression_set`): Asserts "no action outside allowed" for a fixed list of (adversarial_string, injection_key) pairs derived from golden scenarios plus edge cases. Does not require hypothesis; deterministic. Run with `pytest tests/test_security_property_fuzz.py::test_property_no_action_outside_allowed_regression_set -v`.

## CI

- **Smoke:** The default test job runs `pytest -q`, which includes `tests/test_metamorphic_properties.py`. A dedicated step runs `pytest tests/test_metamorphic_properties.py -q` so metamorphic properties are explicitly part of smoke.
- **Policy:** `labtrust validate-policy` runs in a separate job; the fuzzer and metamorphic tests assume policy and tool schemas are valid when used with a repo policy root.
- **Fuzz failures:** The directory `runs/fuzz_failures/` is created on demand when the fuzz harness writes a reproducer. It is not required to exist in the repo; add `runs/fuzz_failures/.gitkeep` if you want the directory under version control.

## Summary

| Mechanism        | Purpose                                      | Deterministic | CI        |
|------------------|----------------------------------------------|---------------|-----------|
| Fuzz harness     | Find contract violations, non-determinism    | Yes (seed)    | Optional  |
| Metamorphic tests| Prove relations across input transformations| Yes (seed)    | Smoke     |
| Reproducers      | Minimal YAML in `runs/fuzz_failures/`       | N/A           | On failure|
