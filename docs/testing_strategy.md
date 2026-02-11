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

Running **`pytest -v`** from the repo root executes all tests, including PettingZoo env smoke (`test_pz_parallel_smoke`, `test_pz_aec_smoke`), benchmark smoke (`test_benchmark_smoke`), and CLI smoke matrix. Expected result: **1059 passed, 51 skipped** in about 10 minutes. Skipped tests are intentional (optional MARL smoke, golden suite when `LABTRUST_RUN_GOLDEN` is unset, live-LLM or missing backends). For a faster run, use `pytest -q` with optional `--ignore=tests/test_pz_parallel_smoke.py --ignore=tests/test_pz_aec_smoke.py --ignore=tests/test_benchmark_smoke.py` to exclude the heaviest smoke tests.

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
