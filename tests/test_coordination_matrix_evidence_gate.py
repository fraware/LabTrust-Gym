"""Evidence gate: matrix fixture inputs satisfy coordination_matrix_inputs policy (roles, paths, portability)."""

import csv
import json
from pathlib import Path

import pytest
import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        header = next(r, None)
    if header is None:
        raise AssertionError(f"Empty CSV: {path}")
    return [h.strip() for h in header]


def test_coordination_matrix_fixture_inputs_match_policy() -> None:
    """Matrix fixture inputs must satisfy coordination_matrix_inputs policy: required roles, path allowlists, portability."""
    root = _repo_root()
    matrix_path = root / "tests" / "fixtures" / "coordination_matrix_fixture.v0.1.json"
    inputs_policy_path = root / "policy" / "coordination" / "coordination_matrix_inputs.v0.1.yaml"

    if not matrix_path.exists() or not inputs_policy_path.exists():
        pytest.skip("coordination matrix fixture or inputs policy not found")

    m = _load_json(matrix_path)
    p = _load_yaml(inputs_policy_path)

    # Phase 1 policy shape has no admissible_inputs.roles; evidence gate applies to north-star shape only.
    if "admissible_inputs" not in p or "roles" not in p.get("admissible_inputs", {}):
        pytest.skip("inputs policy has no admissible_inputs.roles (Phase 1 shape)")

    assert m["spec"]["scope"]["pipeline_mode"] == p["scope"]["pipeline_mode"] == "llm_live"
    assert m["spec"]["scope"]["allow_network"] is True
    assert p["scope"]["allow_network"] is True

    roles = p["admissible_inputs"]["roles"]

    present_roles = {x["role"] for x in m["inputs"]}
    for role_name, role_spec in roles.items():
        if role_spec.get("required", False):
            assert role_name in present_roles, f"Missing required evidence role: {role_name}"

    for entry in m["inputs"]:
        role = entry["role"]
        assert role in roles, f"Unknown evidence role: {role}"

        rel_path = entry["path"]
        assert not rel_path.startswith("/"), "Absolute paths forbidden in matrix inputs."
        assert not rel_path.startswith("~/"), "Home-relative paths forbidden in matrix inputs."

        role_spec = roles[role]

        if "allowed_paths" in role_spec:
            assert rel_path in role_spec["allowed_paths"], f"{role} path not allowed: {rel_path}"

        if "allowed_filenames" in role_spec:
            assert Path(rel_path).name in role_spec["allowed_filenames"], (
                f"{role} filename not allowed: {rel_path}"
            )

    for entry in m["inputs"]:
        role = entry["role"]
        role_spec = roles[role]
        required_cols = role_spec.get("required_columns")
        if required_cols:
            fp = root / entry["path"]
            if fp.exists():
                header = _read_csv_header(fp)
                missing = [c for c in required_cols if c not in header]
                assert not missing, f"{role} missing columns {missing} in {fp}"
