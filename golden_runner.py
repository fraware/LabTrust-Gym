from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# -----------------------------
# Environment Adapter Interface
# -----------------------------
class LabTrustEnvAdapter:
    """
    Your simulator should implement this thin interface.

    Key design rule:
      - The golden runner is the oracle. The engine is a black box that must return enough
        structured data for the oracle to normalize and assert.
    """

    def reset(
        self, initial_state: Dict[str, Any], *, deterministic: bool, rng_seed: int
    ) -> None:
        """Reset the simulator to the scenario initial state."""
        raise NotImplementedError

    def step(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply one event.

        Must return a dict containing at minimum:
          - status: "ACCEPTED" | "BLOCKED"
          - emits: [str] (optional; empty list if none)
          - violations: list of {invariant_id, status, reason_code?, message?} (optional)
          - blocked_reason_code: str|None (required if status == BLOCKED)
          - token_consumed: [token_id] (optional)
          - hashchain: {head_hash, length, last_event_hash} (required)
          - (optional) state_snapshot: any data you want to expose for assertions
        """
        raise NotImplementedError

    def query(self, expr: str) -> Any:
        """
        Query a computed property for state_assertions in the golden YAML.

        Example expr strings used in scenarios:
          - "queue_head(DEV_CHEM_A_01)"
          - "zone_state('Z_RESTRICTED_BIOHAZARD')"
          - "result_status('RES_QC1')"
          - "system_state('log_frozen')"
        """
        raise NotImplementedError


# -----------------------------
# Normalization + Assertion
# -----------------------------
@dataclass
class Failure:
    event_id: str
    message: str
    details: Dict[str, Any]


@dataclass
class StepReport:
    event_id: str
    t_s: int
    agent_id: str
    action_type: str
    status: str
    emits: List[str]
    violations: List[Dict[str, Any]]
    blocked_reason_code: Optional[str]
    token_consumed: List[str]
    state_assertions_checked: List[str]
    hashchain: Dict[str, Any]
    raw_engine_result: Dict[str, Any]


@dataclass
class ScenarioReport:
    scenario_id: str
    title: str
    passed: bool
    failures: List[Failure]
    step_reports: List[StepReport]


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _require(d: Dict[str, Any], k: str, event_id: str) -> Any:
    if k not in d:
        raise AssertionError(f"[{event_id}] Engine result missing required field: {k}")
    return d[k]


def _normalize_violation(v: Dict[str, Any]) -> Dict[str, Any]:
    # Allow engines to return additional fields; runner only normalizes the core.
    return {
        "invariant_id": v.get("invariant_id"),
        "status": v.get("status"),
        "reason_code": v.get("reason_code"),
        "message": v.get("message"),
    }


def _parse_expected_violation_token(s: str) -> Tuple[str, str]:
    # e.g., "INV-ZONE-002:PASS" or "INV-CRIT-004:VIOLATION"
    if ":" not in s:
        raise ValueError(f"Invalid violation token format: {s}")
    inv, st = s.split(":", 1)
    st = st.strip().upper()
    if st not in ("PASS", "VIOLATION"):
        raise ValueError(f"Invalid violation status in token: {s}")
    return inv.strip(), st


def _violation_index(
    violations: List[Dict[str, Any]],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    idx: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for v in violations:
        inv = v.get("invariant_id")
        st = v.get("status")
        if inv and st:
            idx[(inv, st)] = v
    return idx


def _assert_equals(actual: Any, expected: Any, msg: str) -> None:
    if actual != expected:
        raise AssertionError(f"{msg} | expected={expected!r}, actual={actual!r}")


def _assert_contains(container: List[Any], item: Any, msg: str) -> None:
    if item not in container:
        raise AssertionError(f"{msg} | missing={item!r}, container={container!r}")


def _assert_all_contains(container: List[Any], items: List[Any], msg: str) -> None:
    for it in items:
        _assert_contains(container, it, msg)


# -----------------------------
# Golden Runner
# -----------------------------
class GoldenRunner:
    def __init__(self, env: LabTrustEnvAdapter):
        self.env = env

    def run_suite(self, suite_yaml_path: str) -> Dict[str, Any]:
        suite = _load_yaml(Path(suite_yaml_path))
        suite_meta = suite.get("golden_suite", {})
        suite_version = suite_meta.get("version", "unknown")

        rng_seed = int(suite_meta.get("deterministic", {}).get("rng_seed", 0))
        scenario_reports: List[ScenarioReport] = []

        for scen in suite_meta.get("scenarios", []):
            scenario_reports.append(self._run_scenario(scen, rng_seed=rng_seed))

        out = {
            "suite_version": suite_version,
            "scenario_reports": [dataclasses.asdict(sr) for sr in scenario_reports],
        }
        return out

    def _run_scenario(self, scen: Dict[str, Any], *, rng_seed: int) -> ScenarioReport:
        scenario_id = scen["scenario_id"]
        title = scen.get("title", "")
        failures: List[Failure] = []
        step_reports: List[StepReport] = []

        try:
            initial_state = scen.get("initial_state", {})
            self.env.reset(initial_state, deterministic=True, rng_seed=rng_seed)

            for step in scen.get("script", []):
                event_id = step["event_id"]
                try:
                    sr = self._run_step(step)
                    step_reports.append(sr)
                except AssertionError as e:
                    failures.append(
                        Failure(
                            event_id=event_id, message=str(e), details={"step": step}
                        )
                    )
                    step_reports.append(
                        StepReport(
                            event_id=event_id,
                            t_s=int(step.get("t_s", 0)),
                            agent_id=str(step.get("agent_id", "")),
                            action_type=str(step.get("action_type", "")),
                            status="BLOCKED",
                            emits=[],
                            violations=[],
                            blocked_reason_code="RUNNER_ASSERTION_FAILED",
                            token_consumed=[],
                            state_assertions_checked=[],
                            hashchain={
                                "head_hash": "",
                                "length": 0,
                                "last_event_hash": "",
                            },
                            raw_engine_result={},
                        )
                    )
                    # For golden runs, fail-fast per scenario
                    break

        except AssertionError as e:
            failures.append(
                Failure(
                    event_id="__RESET__", message=str(e), details={"scenario": scen}
                )
            )

        passed = len(failures) == 0
        return ScenarioReport(
            scenario_id=scenario_id,
            title=title,
            passed=passed,
            failures=failures,
            step_reports=step_reports,
        )

    def _run_step(self, step: Dict[str, Any]) -> StepReport:
        expect = step.get("expect", {})
        event = {
            "event_id": step["event_id"],
            "t_s": step["t_s"],
            "agent_id": step["agent_id"],
            "action_type": step["action_type"],
            "args": step.get("args", {}),
            "reason_code": step.get("reason_code"),
            "token_refs": step.get("token_refs", []),
        }

        result = self.env.step(event)

        # Required fields (contract)
        status = _require(result, "status", event["event_id"])
        hashchain = _require(result, "hashchain", event["event_id"])

        emits = result.get("emits", [])
        violations = [_normalize_violation(v) for v in result.get("violations", [])]
        blocked_reason_code = result.get("blocked_reason_code")
        token_consumed = result.get("token_consumed", [])

        # Normalize violations index
        v_idx = _violation_index(violations)

        # --------- Oracle assertions ----------
        if "status" in expect:
            _assert_equals(
                status, expect["status"], f"[{event['event_id']}] status mismatch"
            )

        if status == "BLOCKED":
            # In blocked cases, engine must provide blocked_reason_code (unless runner itself blocked)
            if expect.get("blocked_reason_code"):
                _assert_equals(
                    blocked_reason_code,
                    expect["blocked_reason_code"],
                    f"[{event['event_id']}] blocked_reason_code mismatch",
                )
            else:
                if blocked_reason_code is None:
                    raise AssertionError(
                        f"[{event['event_id']}] BLOCKED but blocked_reason_code is null"
                    )

        if "emits" in expect:
            _assert_all_contains(
                emits, expect["emits"], f"[{event['event_id']}] missing emitted events"
            )

        if "violations" in expect:
            for tok in expect["violations"]:
                inv, st = _parse_expected_violation_token(tok)
                if (inv, st) not in v_idx:
                    raise AssertionError(
                        f"[{event['event_id']}] expected violation token missing: {tok} | got={violations}"
                    )

        if "token_consumed" in expect:
            for tid in expect["token_consumed"]:
                _assert_contains(
                    token_consumed,
                    tid,
                    f"[{event['event_id']}] expected token not consumed",
                )

        # state_assertions: strings evaluated via env.query(expr)
        checked: List[str] = []
        if "state_assertions" in expect:
            for expr in expect["state_assertions"]:
                # The YAML may store expressions as already-evaluable string constraints.
                # Convention: "lhs == 'rhs'" where lhs is env.query(...) expression.
                # Example: "zone_state('Z_RESTRICTED_BIOHAZARD') == 'frozen'"
                if "==" not in expr:
                    raise AssertionError(
                        f"[{event['event_id']}] invalid state_assertion: {expr}"
                    )
                lhs, rhs = expr.split("==", 1)
                lhs = lhs.strip()
                rhs = rhs.strip().strip("'").strip('"')
                actual = self.env.query(lhs)
                _assert_equals(
                    str(actual),
                    rhs,
                    f"[{event['event_id']}] state_assertion failed: {expr}",
                )
                checked.append(expr)

        if "state" in expect:
            # Optional structured assertions; leave as pass-through for future extension.
            checked.append("structured_state_assertions_present")

        # Hashchain minimal checks
        _require(hashchain, "head_hash", event["event_id"])
        _require(hashchain, "length", event["event_id"])
        _require(hashchain, "last_event_hash", event["event_id"])

        return StepReport(
            event_id=event["event_id"],
            t_s=int(event["t_s"]),
            agent_id=str(event["agent_id"]),
            action_type=str(event["action_type"]),
            status=str(status),
            emits=list(emits),
            violations=violations,
            blocked_reason_code=blocked_reason_code,
            token_consumed=list(token_consumed),
            state_assertions_checked=checked,
            hashchain=dict(hashchain),
            raw_engine_result=result,
        )


# At top-level imports
from emits_validator import load_emits_vocab, validate_emits


# In GoldenRunner.__init__
class GoldenRunner:
    def __init__(
        self,
        env: LabTrustEnvAdapter,
        *,
        emits_vocab_path: str = "emits_vocab.v0.1.yaml",
    ):
        self.env = env
        self.allowed_emits = load_emits_vocab(emits_vocab_path)


# In _run_step right after emits = result.get("emits", [])
validate_emits(emits, self.allowed_emits, event_id=event["event_id"])
