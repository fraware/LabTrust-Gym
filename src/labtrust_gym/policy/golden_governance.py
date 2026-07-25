"""Golden-suite hazard coverage gate (LTG-PR3).

Fail-closed checks:
- Every golden scenario has governance metadata.
- governance.coverage_class exists in the hazard matrix.
- scenario_id is listed under that class's golden_scenario_ids.
- action_sequence matches script action_type order.
- Uncovered matrix classes must carry a non-empty gap string.
- Matrix golden_scenario_ids must refer to scenarios that exist in the suite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import PolicyLoadError, load_policy_file

HAZARD_MATRIX_REL = "policy/coverage/hazard_coverage_matrix.v0.1.yaml"
GOLDEN_SUITE_REL = "policy/golden/golden_scenarios.v0.1.yaml"

COVERAGE_CLASSES: frozenset[str] = frozenset(
    {
        "specimen_identity",
        "chain_of_custody",
        "quality_control_release",
        "critical_result_escalation",
        "stability_windows",
        "role_authorization",
        "zone_access",
        "token_validity",
        "catalog_drift",
        "multi_site_handoff",
        "adversarial_coordination",
        "insider_misuse",
    }
)


def _action_sequence_from_script(script: list[Any]) -> list[str]:
    out: list[str] = []
    for step in script:
        if not isinstance(step, dict):
            continue
        at = step.get("action_type")
        if at is None:
            continue
        out.append(str(at))
    return out


def _matrix_by_class(matrix_root: dict[str, Any]) -> dict[str, dict[str, Any]]:
    hazards = (matrix_root.get("hazard_coverage_matrix") or {}).get("hazards") or []
    by_class: dict[str, dict[str, Any]] = {}
    for row in hazards:
        if not isinstance(row, dict):
            continue
        hc = row.get("hazard_class")
        if hc:
            by_class[str(hc)] = row
    return by_class


def validate_golden_hazard_coverage_gate(root: Path) -> list[str]:
    """
    Cross-check golden scenarios against the hazard coverage matrix.

    Returns a list of error messages (empty if the gate passes).
    """
    errors: list[str] = []
    root = Path(root)
    golden_path = root / GOLDEN_SUITE_REL
    matrix_path = root / HAZARD_MATRIX_REL

    if not golden_path.exists():
        return [f"{golden_path}: golden suite missing"]
    if not matrix_path.exists():
        return [f"{matrix_path}: hazard coverage matrix missing"]

    try:
        golden_data = load_policy_file(golden_path)
        matrix_data = load_policy_file(matrix_path)
    except PolicyLoadError as e:
        return [str(e)]

    if not isinstance(golden_data, dict) or not isinstance(matrix_data, dict):
        return [f"{golden_path}: expected mapping roots for golden suite and matrix"]

    suite = golden_data.get("golden_suite") or {}
    scenarios = suite.get("scenarios") or []
    if not isinstance(scenarios, list) or not scenarios:
        errors.append(f"{golden_path}: golden_suite.scenarios missing or empty")
        return errors

    by_class = _matrix_by_class(matrix_data)
    if not by_class:
        errors.append(f"{matrix_path}: hazard_coverage_matrix.hazards missing or empty")
        return errors

    # Uncovered classes must keep an explicit gap (fail-closed inventory).
    for hc, row in sorted(by_class.items()):
        coverage = row.get("coverage")
        gap = row.get("gap")
        if coverage == "uncovered":
            if not (isinstance(gap, str) and gap.strip()):
                errors.append(
                    f"{matrix_path}: hazard_class={hc!r} coverage=uncovered requires non-empty gap"
                )
            gs_ids = row.get("golden_scenario_ids") or []
            if gs_ids:
                errors.append(
                    f"{matrix_path}: hazard_class={hc!r} coverage=uncovered must not list "
                    f"golden_scenario_ids (found {gs_ids!r}); keep as explicit gap"
                )

        if hc not in COVERAGE_CLASSES:
            errors.append(f"{matrix_path}: unknown hazard_class={hc!r}")

    suite_ids: set[str] = set()
    for i, sc in enumerate(scenarios):
        if not isinstance(sc, dict):
            errors.append(f"{golden_path}: scenarios[{i}] is not an object")
            continue
        sid = sc.get("scenario_id")
        if not sid:
            errors.append(f"{golden_path}: scenarios[{i}] missing scenario_id")
            continue
        sid_s = str(sid)
        suite_ids.add(sid_s)
        gov = sc.get("governance")
        if not isinstance(gov, dict):
            errors.append(f"{golden_path}: {sid_s}: missing governance object")
            continue

        cc = gov.get("coverage_class")
        if not cc or str(cc) not in COVERAGE_CLASSES:
            errors.append(
                f"{golden_path}: {sid_s}: coverage_class={cc!r} is not a known matrix class"
            )
            continue
        cc_s = str(cc)
        row = by_class.get(cc_s)
        if row is None:
            errors.append(
                f"{golden_path}: {sid_s}: coverage_class={cc_s!r} has no matrix entry"
            )
            continue
        matrix_ids = [str(x) for x in (row.get("golden_scenario_ids") or [])]
        if sid_s not in matrix_ids:
            errors.append(
                f"{golden_path}: {sid_s}: claims coverage_class={cc_s!r} but is not listed in "
                f"{matrix_path} golden_scenario_ids for that class (fail-closed coverage gate)"
            )

        script = sc.get("script") or []
        if not isinstance(script, list):
            errors.append(f"{golden_path}: {sid_s}: script must be a list")
            continue
        derived = _action_sequence_from_script(script)
        declared = gov.get("action_sequence")
        if not isinstance(declared, list):
            errors.append(f"{golden_path}: {sid_s}: governance.action_sequence must be a list")
        else:
            declared_s = [str(x) for x in declared]
            if declared_s != derived:
                errors.append(
                    f"{golden_path}: {sid_s}: governance.action_sequence {declared_s!r} "
                    f"does not match script action_type order {derived!r}"
                )

        # Required string fields (schema also enforces; keep gate self-contained).
        for key in (
            "hazard",
            "policy_version",
            "expected_terminal_state",
            "reviewer",
        ):
            val = gov.get(key)
            if not (isinstance(val, str) and val.strip()):
                errors.append(f"{golden_path}: {sid_s}: governance.{key} must be a non-empty string")

        erc = gov.get("expected_reason_codes")
        if not isinstance(erc, list):
            errors.append(f"{golden_path}: {sid_s}: governance.expected_reason_codes must be a list")
        revid = gov.get("required_evidence")
        if not isinstance(revid, list) or not revid:
            errors.append(
                f"{golden_path}: {sid_s}: governance.required_evidence must be a non-empty list"
            )

    # Orphan matrix IDs (listed but missing from suite).
    for hc, row in sorted(by_class.items()):
        for mid in row.get("golden_scenario_ids") or []:
            mid_s = str(mid)
            if mid_s not in suite_ids:
                errors.append(
                    f"{matrix_path}: hazard_class={hc!r} lists unknown golden_scenario_id={mid_s!r}"
                )

    return errors
