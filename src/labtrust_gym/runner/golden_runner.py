"""
Golden runner: run scenario suite against an env adapter and assert the contract.

Loads golden scenarios from policy/golden; for each scenario, resets the env
to initial_state and replays steps (or runs an oracle). Asserts that step
outputs match expectations (status, violations, state_assertions) and that all
emits are in the policy emit vocabulary. Output shape matches
policy/schemas/runner_output_contract.v0.1.schema.json. Unknown emits cause
AssertionError in _run_step via validate_emits.
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from labtrust_gym.runner.adapter import LabTrustEnvAdapter
from labtrust_gym.runner.emits_validator import load_emits_vocab, validate_emits


# -----------------------------
# Normalization + Assertion
# -----------------------------
@dataclass
class Failure:
    event_id: str
    message: str
    details: dict[str, Any]


@dataclass
class StepReport:
    event_id: str
    t_s: int
    agent_id: str
    action_type: str
    status: str
    emits: list[str]
    violations: list[dict[str, Any]]
    blocked_reason_code: str | None
    token_consumed: list[str]
    state_assertions_checked: list[str]
    hashchain: dict[str, Any]
    raw_engine_result: dict[str, Any]
    raw_event: dict[str, Any] | None = None


@dataclass
class ScenarioReport:
    scenario_id: str
    title: str
    passed: bool
    failures: list[Failure]
    step_reports: list[StepReport]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return cast(dict[str, Any], yaml.safe_load(f))


def _require(d: dict[str, Any], k: str, event_id: str) -> Any:
    if k not in d:
        raise AssertionError(f"[{event_id}] Engine result missing required field: {k}")
    return d[k]


def _normalize_violation(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "invariant_id": v.get("invariant_id"),
        "status": v.get("status"),
        "reason_code": v.get("reason_code"),
        "message": v.get("message"),
    }


def _parse_expected_violation_token(s: str) -> tuple[str, str]:
    if ":" not in s:
        raise ValueError(f"Invalid violation token format: {s}")
    inv, st = s.split(":", 1)
    st = st.strip().upper()
    if st not in ("PASS", "VIOLATION"):
        raise ValueError(f"Invalid violation status in token: {s}")
    return inv.strip(), st


def _violation_index(
    violations: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    idx: dict[tuple[str, str], dict[str, Any]] = {}
    for v in violations:
        inv = v.get("invariant_id")
        st = v.get("status")
        if inv and st:
            idx[(inv, st)] = v
    return idx


def _assert_equals(actual: Any, expected: Any, msg: str) -> None:
    if actual != expected:
        raise AssertionError(f"{msg} | expected={expected!r}, actual={actual!r}")


def _assert_contains(container: list[Any], item: Any, msg: str) -> None:
    if item not in container:
        raise AssertionError(f"{msg} | missing={item!r}, container={container!r}")


def _assert_all_contains(container: list[Any], items: list[Any], msg: str) -> None:
    for it in items:
        _assert_contains(container, it, msg)


def _build_episode_log_entries(
    step_reports: list[StepReport],
) -> list[dict[str, Any]]:
    """Build JSONL-style entries from step reports for export_receipts."""
    from labtrust_gym.logging.episode_log import build_log_entry

    entries: list[dict[str, Any]] = []
    for sr in step_reports:
        if sr.raw_event is None or not sr.raw_engine_result:
            continue
        entry = build_log_entry(
            sr.raw_event,
            sr.raw_engine_result,
        )
        entries.append(entry)
    return entries


def _write_episode_log(path: Path, entries: list[dict[str, Any]]) -> None:
    """Write episode log JSONL (deterministic: sort_keys=True)."""
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, sort_keys=True) + "\n")


# -----------------------------
# Post-run hook helpers (deterministic; use stable paths for golden runs)
# -----------------------------
def run_export_receipts(
    episode_log_path: Path,
    out_dir: Path,
    partner_id: str | None = None,
    policy_fingerprint: str | None = None,
) -> Path:
    """Export receipts + evidence bundle from episode log to out_dir. Returns path to EvidenceBundle.v0.1 dir."""
    from labtrust_gym.export.receipts import export_receipts

    return export_receipts(episode_log_path, out_dir, policy_fingerprint=policy_fingerprint, partner_id=partner_id)


def run_verify_bundle(bundle_dir: Path, policy_root: Path | None = None) -> tuple[bool, str, list[str]]:
    """Run verify_bundle on bundle_dir. Returns (passed, report_text, errors)."""
    from labtrust_gym.export.verify import verify_bundle

    return verify_bundle(bundle_dir, policy_root=policy_root, allow_extra_files=False)


def run_export_fhir(receipts_dir: Path, out_dir: Path, out_filename: str = "fhir_bundle.json") -> Path:
    """Export FHIR bundle from receipts dir to out_dir. Returns path to output file."""
    from labtrust_gym.export.fhir_r4 import export_fhir

    return export_fhir(receipts_dir, out_dir, out_filename=out_filename)


# -----------------------------
# Golden Runner
# -----------------------------
def _strict_reason_codes_from_env() -> bool:
    """True when LABTRUST_STRICT_REASON_CODES=1."""
    return os.environ.get("LABTRUST_STRICT_REASON_CODES") == "1"


class GoldenRunner:
    def __init__(
        self,
        env: LabTrustEnvAdapter,
        *,
        emits_vocab_path: str = "policy/emits/emits_vocab.v0.1.yaml",
        reason_code_registry_path: str | None = None,
        strict_reason_codes: bool | None = None,
        policy_root: str | Path | None = None,
    ):
        self.env = env
        self.allowed_emits = load_emits_vocab(emits_vocab_path)
        self._policy_root = Path(policy_root) if policy_root else Path.cwd()
        strict = strict_reason_codes if strict_reason_codes is not None else _strict_reason_codes_from_env()
        self._reason_registry: dict[str, dict[str, Any]] = {}
        if strict:
            from labtrust_gym.policy.reason_codes import load_reason_code_registry

            path = reason_code_registry_path or "policy/reason_codes/reason_code_registry.v0.1.yaml"
            p = Path(path)
            if not p.is_absolute():
                p = Path.cwd() / p
            if p.exists():
                self._reason_registry = load_reason_code_registry(p)
        self._strict_reason_codes = strict and bool(self._reason_registry)

    def run_suite(
        self,
        suite_yaml_path: str,
        work_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        suite = _load_yaml(Path(suite_yaml_path))
        suite_meta = suite.get("golden_suite", {})
        suite_version = suite_meta.get("version", "unknown")

        rng_seed = int(suite_meta.get("deterministic", {}).get("rng_seed", 0))
        scenario_reports: list[ScenarioReport] = []
        base_work = Path(work_dir) if work_dir else None
        fixtures = suite_meta.get("fixtures", {})

        for scen in suite_meta.get("scenarios", []):
            scenario_work = (base_work / scen["scenario_id"]) if base_work else None
            scenario_reports.append(
                self._run_scenario(scen, rng_seed=rng_seed, work_dir=scenario_work, fixtures=fixtures)
            )

        out = {
            "suite_version": suite_version,
            "scenario_reports": [dataclasses.asdict(sr) for sr in scenario_reports],
        }
        return out

    def _run_scenario(
        self,
        scen: dict[str, Any],
        *,
        rng_seed: int,
        work_dir: Path | None = None,
        fixtures: dict[str, Any] | None = None,
    ) -> ScenarioReport:
        scenario_id = scen["scenario_id"]
        title = scen.get("title", "")
        failures: list[Failure] = []
        step_reports: list[StepReport] = []
        fixtures = fixtures or {}

        try:
            initial_state = dict(scen.get("initial_state", {}))
            if "agents" not in initial_state and fixtures.get("agents"):
                initial_state["agents"] = list(fixtures["agents"])
            if self._policy_root is not None and "policy_root" not in initial_state:
                initial_state["policy_root"] = str(self._policy_root)
            if "transport_fault_injection" in scen:
                initial_state["transport_fault_injection"] = scen["transport_fault_injection"]
            self.env.reset(initial_state, deterministic=True, rng_seed=rng_seed)

            for step in scen.get("script", []):
                event_id = step["event_id"]
                try:
                    sr = self._run_step(step)
                    step_reports.append(sr)
                except AssertionError as e:
                    failures.append(Failure(event_id=event_id, message=str(e), details={"step": step}))
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
                            raw_event=None,
                        )
                    )
                    break

        except AssertionError as e:
            failures.append(Failure(event_id="__RESET__", message=str(e), details={"scenario": scen}))

        passed = len(failures) == 0
        if passed and (scen.get("post_run_hooks") or scen.get("post_run")):
            try:
                self._run_post_run_phase(scen, step_reports, failures, work_dir=work_dir)
            except AssertionError as e:
                passed = False
                failures.append(
                    Failure(
                        event_id="__POST_RUN__",
                        message=str(e),
                        details={
                            "post_run_hooks": scen.get("post_run_hooks"),
                            "post_run": scen.get("post_run"),
                        },
                    )
                )

        return ScenarioReport(
            scenario_id=scenario_id,
            title=title,
            passed=passed,
            failures=failures,
            step_reports=step_reports,
        )

    def _run_step(self, step: dict[str, Any]) -> StepReport:
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
        if "key_id" in step:
            event["key_id"] = step["key_id"]
        if "signature" in step:
            event["signature"] = step["signature"]
        if "rationale" in step:
            event["rationale"] = step["rationale"]

        result = self.env.step(event)

        status = _require(result, "status", event["event_id"])
        hashchain = _require(result, "hashchain", event["event_id"])

        emits = result.get("emits", [])
        validate_emits(emits, self.allowed_emits, event_id=event["event_id"])

        if self._strict_reason_codes:
            from labtrust_gym.policy.reason_codes import validate_reason_code

            validate_reason_code(
                result.get("blocked_reason_code"),
                self._reason_registry,
                event_id=event["event_id"],
                context="blocked_reason_code",
            )
            validate_reason_code(
                event.get("reason_code"),
                self._reason_registry,
                event_id=event["event_id"],
                context="reason_code",
            )

        violations = [_normalize_violation(v) for v in result.get("violations", [])]
        blocked_reason_code = result.get("blocked_reason_code")
        token_consumed = result.get("token_consumed", [])

        v_idx = _violation_index(violations)

        if "status" in expect:
            _assert_equals(status, expect["status"], f"[{event['event_id']}] status mismatch")

        if status == "BLOCKED":
            if expect.get("blocked_reason_code"):
                _assert_equals(
                    blocked_reason_code,
                    expect["blocked_reason_code"],
                    f"[{event['event_id']}] blocked_reason_code mismatch",
                )
            else:
                if blocked_reason_code is None:
                    raise AssertionError(f"[{event['event_id']}] BLOCKED but blocked_reason_code is null")

        if "emits" in expect:
            _assert_all_contains(emits, expect["emits"], f"[{event['event_id']}] missing emitted events")

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

        checked: list[str] = []
        if "state_assertions" in expect:
            for expr in expect["state_assertions"]:
                expr = expr.strip()
                if " contains " in expr:
                    lhs, rhs = expr.split(" contains ", 1)
                    lhs = lhs.strip()
                    rhs = rhs.strip().strip("'").strip('"')
                    actual = self.env.query(lhs)
                    if not isinstance(actual, list):
                        actual = [actual] if actual is not None else []
                    _assert_contains(
                        actual,
                        rhs,
                        f"[{event['event_id']}] state_assertion failed: {expr}",
                    )
                    checked.append(expr)
                elif "==" in expr:
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
                else:
                    raise AssertionError(f"[{event['event_id']}] invalid state_assertion: {expr}")

        if "state" in expect:
            checked.append("structured_state_assertions_present")

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
            raw_event=event,
        )

    def _run_post_run_phase(
        self,
        scen: dict[str, Any],
        step_reports: list[StepReport],
        failures: list[Failure],
        work_dir: Path | None = None,
    ) -> None:
        """Run post_run_hooks (if any) then post_run (if any). Uses work_dir or a temp dir."""
        entries = _build_episode_log_entries(step_reports)
        if work_dir is None:
            work_dir = Path(tempfile.mkdtemp(prefix="labtrust_golden_"))
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        episode_log_path = work / "episode_log.jsonl"
        _write_episode_log(episode_log_path, entries)

        receipts_dir: Path | None = None

        hooks = scen.get("post_run_hooks") or []
        for hook in hooks:
            if hook == "EXPORT_RECEIPTS":
                out_sub = work / "receipts"
                out_sub.mkdir(parents=True, exist_ok=True)
                receipts_dir = run_export_receipts(episode_log_path, out_sub)
            elif hook == "VERIFY_BUNDLE":
                bundle_dir = receipts_dir
                if bundle_dir is None:
                    out_sub = work / "receipts"
                    bundle_dir = out_sub / "EvidenceBundle.v0.1"
                    if not bundle_dir.exists():
                        raise AssertionError("VERIFY_BUNDLE requires prior EXPORT_RECEIPTS (no bundle dir found)")
                passed_verify, report, errors = run_verify_bundle(bundle_dir, policy_root=self._policy_root)
                if not passed_verify:
                    raise AssertionError(f"VERIFY_BUNDLE failed: {report}; errors: {errors}")
            elif hook == "EXPORT_FHIR":
                if receipts_dir is None:
                    out_sub = work / "receipts"
                    bundle_sub = out_sub / "EvidenceBundle.v0.1"
                    if not bundle_sub.exists():
                        raise AssertionError("EXPORT_FHIR requires prior EXPORT_RECEIPTS (no bundle dir found)")
                    receipts_dir = bundle_sub
                fhir_out = work / "fhir"
                fhir_out.mkdir(parents=True, exist_ok=True)
                run_export_fhir(receipts_dir, fhir_out, out_filename="fhir_bundle.json")
            else:
                raise AssertionError(f"post_run_hooks unknown hook: {hook}")

        post_run = scen.get("post_run") or []
        if post_run:
            self._run_post_run(post_run, step_reports, failures, work_dir=work, receipts_dir=receipts_dir)

    def _run_post_run(
        self,
        post_run: list[dict[str, Any]],
        step_reports: list[StepReport],
        failures: list[Failure],
        work_dir: Path,
        receipts_dir: Path | None = None,
    ) -> None:
        """Execute post_run actions: export receipts/FHIR, assert file exists/schema valid. work_dir already has episode log and possibly receipts from post_run_hooks."""
        work = Path(work_dir)
        episode_log_path = work / "episode_log.jsonl"

        for action_spec in post_run:
            action = action_spec.get("action")
            if not action:
                raise AssertionError("post_run action missing 'action' field")

            if action == "EXPORT_RECEIPTS":
                out_dir = action_spec.get("out_dir")
                if not out_dir:
                    raise AssertionError("EXPORT_RECEIPTS requires out_dir")
                out_path = work / out_dir
                out_path.mkdir(parents=True, exist_ok=True)
                receipts_dir = run_export_receipts(episode_log_path, out_path)

            elif action == "EXPORT_FHIR":
                out_dir = action_spec.get("out_dir")
                if not out_dir:
                    raise AssertionError("EXPORT_FHIR requires out_dir")
                if receipts_dir is None:
                    raise AssertionError("EXPORT_FHIR requires prior EXPORT_RECEIPTS")
                out_path = work / out_dir
                out_path.mkdir(parents=True, exist_ok=True)
                out_filename = action_spec.get("out_filename", "fhir_bundle.json")
                run_export_fhir(receipts_dir, out_path, out_filename=out_filename)

            elif action == "ASSERT_FILE_EXISTS":
                path_val = action_spec.get("path")
                if not path_val:
                    raise AssertionError("ASSERT_FILE_EXISTS requires path")
                p = work / path_val if not Path(path_val).is_absolute() else Path(path_val)
                if not p.exists():
                    raise AssertionError(f"ASSERT_FILE_EXISTS: file not found: {p}")

            elif action == "ASSERT_SCHEMA_VALID":
                path_val = action_spec.get("path")
                schema_val = action_spec.get("schema")
                if not path_val or not schema_val:
                    raise AssertionError("ASSERT_SCHEMA_VALID requires path and schema")
                p = work / path_val if not Path(path_val).is_absolute() else Path(path_val)
                if not p.exists():
                    raise AssertionError(f"ASSERT_SCHEMA_VALID: file not found: {p}")
                schema_path = self._policy_root / "policy" / "schemas" / schema_val
                if not schema_path.exists():
                    schema_path = self._policy_root / schema_val
                if not schema_path.exists():
                    raise AssertionError(f"ASSERT_SCHEMA_VALID: schema not found: {schema_path}")
                from labtrust_gym.policy.loader import load_json, validate_against_schema

                data = load_json(p)
                schema = load_json(schema_path)
                validate_against_schema(data, schema, path=p)

            else:
                raise AssertionError(f"post_run unknown action: {action}")
