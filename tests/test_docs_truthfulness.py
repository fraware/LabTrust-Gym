"""
Invariant tests to keep docs and policy in sync.

- Golden scenario count: policy/golden/golden_scenarios.v0.1.yaml is the source of truth;
  this test asserts the count so CI fails if someone adds/removes a scenario without
  updating the expected constant (and vice versa).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.policy.loader import load_yaml

# Canonical expected count: must match policy/golden/golden_scenarios.v0.1.yaml.
# Update this constant when adding or removing golden scenarios; CI will fail if
# the policy file has a different count.
EXPECTED_GOLDEN_SCENARIO_COUNT = 35


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_golden_scenario_count_matches_policy() -> None:
    """
    Assert that the number of scenarios in golden_scenarios.v0.1.yaml equals
    EXPECTED_GOLDEN_SCENARIO_COUNT. Prevents drift between docs and the policy file.
    """
    root = _repo_root()
    path = root / "policy" / "golden" / "golden_scenarios.v0.1.yaml"
    if not path.exists():
        pytest.skip(f"Golden scenarios file not found: {path}")
    data = load_yaml(path)
    golden_suite = data.get("golden_suite") or {}
    scenarios = golden_suite.get("scenarios") or []
    count = len(scenarios)
    assert count == EXPECTED_GOLDEN_SCENARIO_COUNT, (
        f"Golden scenario count mismatch: policy has {count}, expected "
        f"{EXPECTED_GOLDEN_SCENARIO_COUNT}. Update EXPECTED_GOLDEN_SCENARIO_COUNT in "
        "tests/test_docs_truthfulness.py and any docs that mention the scenario count when adding/removing scenarios."
    )
