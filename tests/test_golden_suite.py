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

    def reset(self, initial_state, *, deterministic: bool, rng_seed: int) -> None:
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
def test_golden_suite(suite_path: str, tmp_path: Path) -> None:
    """
    Run golden suite: validate runner output against contract schema; fail if any scenario failed.
    Skipped unless LABTRUST_RUN_GOLDEN=1 (CI stays green until engine exists).
    Export dirs (receipts, FHIR) are written under tmp_path when running full suite.
    """
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run golden suite (engine adapter required).")

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
    runner = GoldenRunner(
        env,
        emits_vocab_path=str(emits_path),
        policy_root=root,
    )

    out = runner.run_suite(str(suite_file), work_dir=tmp_path)

    jsonschema.validate(instance=out, schema=schema)

    failed = [r for r in out["scenario_reports"] if not r["passed"]]
    if failed:
        summary = [
            {
                "scenario_id": r["scenario_id"],
                "title": r.get("title", ""),
                "first_failure": (r.get("failures", [{}])[0] if r.get("failures") else None),
            }
            for r in failed
        ]
        pytest.fail("Golden suite failed:\n" + json.dumps(summary, indent=2))


def test_post_run_hooks_parsing_and_execution(tmp_path: Path) -> None:
    """
    Unit test for post_run_hooks: parsing and execution with tmp_path.
    No real engine, no network: uses a fake adapter that returns valid step results.
    Asserts EXPORT_RECEIPTS -> VERIFY_BUNDLE -> EXPORT_FHIR produce expected files.
    """
    from labtrust_gym.runner import GoldenRunner, LabTrustEnvAdapter

    class FakeEnvForHooks(LabTrustEnvAdapter):
        """Minimal adapter: reset no-op, step returns ACCEPTED with hashchain/emits. Hashchain length increments so VERIFY_BUNDLE (proof length == episode_log entries) passes."""

        def __init__(self):
            self._step_count = 0

        def reset(self, initial_state, *, deterministic: bool, rng_seed: int) -> None:
            self._step_count = 0

        def step(self, event):
            self._step_count += 1
            action_type = event.get("action_type", "")
            emit = action_type if action_type else "CREATE_ACCESSION"
            t_s = event.get("t_s", 0)
            return {
                "status": "ACCEPTED",
                "emits": [emit],
                "violations": [],
                "blocked_reason_code": None,
                "token_consumed": [],
                "hashchain": {
                    "head_hash": "fake_head_" + str(t_s),
                    "length": self._step_count,
                    "last_event_hash": "fake_last_" + str(t_s),
                },
                "state_snapshot": {},
            }

        def query(self, expr: str):
            return None

    root = _repo_root()
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        pytest.skip("Emits vocab not found")

    runner = GoldenRunner(
        FakeEnvForHooks(),
        emits_vocab_path=str(emits_path),
        policy_root=root,
    )

    scenario = {
        "scenario_id": "GS-HOOKS-UNIT",
        "title": "Post-run hooks unit test",
        "initial_state": {"system": {"now_s": 0}, "specimens": [], "tokens": []},
        "script": [
            {
                "event_id": "e1",
                "t_s": 100,
                "agent_id": "A_RECEPTION",
                "action_type": "CREATE_ACCESSION",
                "args": {"specimen_id": "S1"},
                "reason_code": None,
                "token_refs": [],
                "expect": {"status": "ACCEPTED", "emits": ["CREATE_ACCESSION"]},
            },
            {
                "event_id": "e2",
                "t_s": 110,
                "agent_id": "A_RECEPTION",
                "action_type": "ACCEPT_SPECIMEN",
                "args": {"specimen_id": "S1"},
                "reason_code": None,
                "token_refs": [],
                "expect": {"status": "ACCEPTED", "emits": ["ACCEPT_SPECIMEN"]},
            },
        ],
        "post_run_hooks": ["EXPORT_RECEIPTS", "VERIFY_BUNDLE", "EXPORT_FHIR"],
    }

    report = runner._run_scenario(scenario, rng_seed=42, work_dir=tmp_path)

    assert report.passed, f"Scenario should pass: {report.failures}"
    # When work_dir is passed to _run_scenario, it is used as the scenario work dir (no scenario_id subdir)
    manifest_path = tmp_path / "receipts" / "EvidenceBundle.v0.1" / "manifest.json"
    assert manifest_path.exists(), f"manifest should exist at {manifest_path}"
    fhir_path = tmp_path / "fhir" / "fhir_bundle.json"
    assert fhir_path.exists(), f"FHIR bundle should exist at {fhir_path}"

    # Minimal structural check: FHIR Bundle
    fhir_data = json.loads(fhir_path.read_text(encoding="utf-8"))
    assert fhir_data.get("resourceType") == "Bundle"
    assert "entry" in fhir_data and isinstance(fhir_data["entry"], list)


def test_golden_shift_change_001(tmp_path: Path) -> None:
    """
    Run GS-SHIFT-CHANGE-001 only: mid-episode roster update, STAT inject, no RELEASE_RESULT
    from reception role, strict mode (all mutating actions signed).
    Skipped unless LABTRUST_RUN_GOLDEN=1.
    """
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run golden scenario GS-SHIFT-CHANGE-001.")

    root = _repo_root()
    suite_file = root / "policy" / "golden" / "golden_scenarios.v0.1.yaml"
    if not suite_file.exists():
        pytest.skip(f"Suite file not found: {suite_file}")

    import yaml

    suite = yaml.safe_load(suite_file.read_text(encoding="utf-8"))
    scenarios = suite.get("golden_suite", {}).get("scenarios", [])
    shift_scen = next(
        (s for s in scenarios if s.get("scenario_id") == "GS-SHIFT-CHANGE-001"),
        None,
    )
    if shift_scen is None:
        pytest.skip("GS-SHIFT-CHANGE-001 not found in golden_scenarios.v0.1.yaml")

    env = _get_env_adapter()
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        pytest.fail("Emits vocab not found")
    runner = GoldenRunner(
        env,
        emits_vocab_path=str(emits_path),
        policy_root=root,
    )

    report = runner._run_scenario(shift_scen, rng_seed=12345, work_dir=tmp_path)

    assert report.passed, f"GS-SHIFT-CHANGE-001 must pass: failures={report.failures!r}"
    assert report.scenario_id == "GS-SHIFT-CHANGE-001"
    assert len(report.step_reports) >= 9
    # Last step: RELEASE_RESULT from A_ANALYTICS (reception role) -> BLOCKED
    last_sr = report.step_reports[-1]
    assert last_sr.action_type == "RELEASE_RESULT"
    assert last_sr.status == "BLOCKED"
    assert last_sr.blocked_reason_code == "RBAC_ACTION_DENY"
