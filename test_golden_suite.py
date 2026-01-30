import json
from pathlib import Path

import jsonschema
import pytest

from golden_runner import GoldenRunner, LabTrustEnvAdapter


class TODO_LabTrustEnv(LabTrustEnvAdapter):
    """
    Replace this with your real simulator adapter.

    Until the engine exists, this class can be used with a minimal fake environment
    to validate the runner mechanics. In CI, you should always run against the real engine.
    """

    def reset(self, initial_state, *, deterministic: bool, rng_seed: int):
        raise NotImplementedError("Wire your simulator here.")

    def step(self, event):
        raise NotImplementedError("Wire your simulator here.")

    def query(self, expr: str):
        raise NotImplementedError("Wire your simulator here.")


@pytest.mark.parametrize(
    "suite_path",
    [
        "golden_scenarios.v0.1.yaml",
    ],
)
def test_golden_suite(suite_path: str):
    schema = json.loads(
        Path("runner_output_contract.v0.1.schema.json").read_text(encoding="utf-8")
    )

    env = TODO_LabTrustEnv()
    runner = GoldenRunner(env)

    out = runner.run_suite(suite_path)

    # Validate runner output structure
    jsonschema.validate(instance=out, schema=schema)

    # Fail the test if any scenario failed
    failed = [r for r in out["scenario_reports"] if not r["passed"]]
    if failed:
        # Print a focused summary
        summary = []
        for r in failed:
            fails = r.get("failures", [])
            summary.append(
                {
                    "scenario_id": r["scenario_id"],
                    "title": r.get("title", ""),
                    "first_failure": fails[0] if fails else None,
                }
            )
        pytest.fail("Golden suite failed:\n" + json.dumps(summary, indent=2))
