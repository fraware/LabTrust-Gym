"""
Golden suite: run scenarios against env adapter and validate runner output contract.

- Loads schema policy/schemas/runner_output_contract.v0.1.schema.json.
- Validates runner output via jsonschema.
- Fails if any scenario failed.

When LABTRUST_RUN_GOLDEN=1 uses real engine (CoreEnv); otherwise uses
PlaceholderLabTrustEnv and skips so CI stays green.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import jsonschema
import pytest

from labtrust_gym.runner import GoldenRunner, LabTrustEnvAdapter


def _get_env_adapter():  # type: () -> LabTrustEnvAdapter
    """Return real engine when LABTRUST_RUN_GOLDEN=1, else placeholder."""
    if os.environ.get("LABTRUST_RUN_GOLDEN") == "1":
        from labtrust_gym.engine.core_env import CoreEnv
        return CoreEnv()
    return PlaceholderLabTrustEnv()


class PlaceholderLabTrustEnv(LabTrustEnvAdapter):
    """
    Placeholder adapter: raises NotImplementedError.
    Used when LABTRUST_RUN_GOLDEN is not set so tests are skipped.
    """

    def reset(
        self, initial_state, *, deterministic: bool, rng_seed: int
    ) -> None:
        raise NotImplementedError("Engine adapter not implemented.")

    def step(self, event):
        raise NotImplementedError("Engine adapter not implemented.")

    def query(self, expr: str):
        raise NotImplementedError("Engine adapter not implemented.")


def _repo_root() -> Path:
    """Project root (parent of tests)."""
    return Path(__file__).resolve().parent.parent


def _should_run_golden() -> bool:
    """Run golden suite only when LABTRUST_RUN_GOLDEN=1."""
    return os.environ.get("LABTRUST_RUN_GOLDEN") == "1"


@pytest.mark.parametrize(
    "suite_path",
    [
        "policy/golden/golden_scenarios.v0.1.yaml",
        "golden_scenarios.v0.1.yaml",
    ],
)
def test_golden_suite(suite_path: str) -> None:
    """
    Run golden suite: validate runner output against contract schema; fail if any scenario failed.
    Skipped unless LABTRUST_RUN_GOLDEN=1 (CI stays green until engine exists).
    """
    if not _should_run_golden():
        pytest.skip(
            "Set LABTRUST_RUN_GOLDEN=1 to run golden suite (engine adapter required)."
        )

    root = _repo_root()
    suite_file = root / suite_path
    if not suite_file.exists():
        pytest.skip(f"Suite file not found: {suite_file}")

    schema_path = root / "policy" / "schemas" / "runner_output_contract.v0.1.schema.json"
    if not schema_path.exists():
        schema_path = root / "runner_output_contract.v0.1.schema.json"
    if not schema_path.exists():
        pytest.fail(f"Runner output contract schema not found: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    env = _get_env_adapter()
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        pytest.fail(f"Emits vocab not found: {emits_path}")
    runner = GoldenRunner(env, emits_vocab_path=str(emits_path))

    out = runner.run_suite(str(suite_file))

    jsonschema.validate(instance=out, schema=schema)

    failed = [r for r in out["scenario_reports"] if not r["passed"]]
    if failed:
        summary = [
            {
                "scenario_id": r["scenario_id"],
                "title": r.get("title", ""),
                "first_failure": r.get("failures", [{}])[0] if r.get("failures") else None,
            }
            for r in failed
        ]
        pytest.fail("Golden suite failed:\n" + json.dumps(summary, indent=2))
