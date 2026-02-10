"""Contract gate: coordination matrix artifact validates against schema and invariants."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(schema: dict, instance: dict) -> None:
    v = Draft202012Validator(schema)
    errors = sorted(v.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        msg = "\n".join([f"{list(e.path)}: {e.message}" for e in errors])
        raise AssertionError(f"Schema validation failed:\n{msg}")


def test_coordination_matrix_fixture_validates_schema() -> None:
    """Fixture coordination_matrix_fixture.v0.1.json must validate against coordination_matrix.v0.1 schema."""
    root = _repo_root()
    fixture = root / "tests" / "fixtures" / "coordination_matrix_fixture.v0.1.json"
    schema_path = root / "policy" / "schemas" / "coordination_matrix.v0.1.schema.json"

    if not fixture.exists() or not schema_path.exists():
        pytest.skip("coordination matrix fixture or schema not found")

    instance = _load_json(fixture)
    schema = _load_json(schema_path)
    _validate(schema, instance)


def test_coordination_matrix_live_only_invariants() -> None:
    """Matrix spec scope and every row run_meta must be llm_live, allow_network true, allowed backends/methods."""
    root = _repo_root()
    fixture = root / "tests" / "fixtures" / "coordination_matrix_fixture.v0.1.json"
    if not fixture.exists():
        pytest.skip("coordination matrix fixture not found")
    m = _load_json(fixture)

    assert m["spec"]["scope"]["pipeline_mode"] == "llm_live"
    assert m["spec"]["scope"]["allow_network"] is True

    for row in m["rows"]:
        meta = row["run_meta"]
        assert meta["pipeline_mode"] == "llm_live"
        assert meta["allow_network"] is True
        assert meta["llm_backend_id"] in m["spec"]["scope"]["allowed_llm_backends"]
        assert row["method_id"] in m["spec"]["scope"]["allowed_methods"]


def test_coordination_matrix_rank_consistency_per_scale() -> None:
    """CQ and AR ranks must be unique per scale where present."""
    root = _repo_root()
    fixture = root / "tests" / "fixtures" / "coordination_matrix_fixture.v0.1.json"
    if not fixture.exists():
        pytest.skip("coordination matrix fixture not found")
    m = _load_json(fixture)

    rows_by_scale: dict[str, list] = {}
    for r in m["rows"]:
        rows_by_scale.setdefault(r["scale_id"], []).append(r)

    for scale_id, rows in rows_by_scale.items():
        cq_ranks = [r["ranks"]["cq_rank"] for r in rows if r["ranks"]["cq_rank"] is not None]
        ar_ranks = [r["ranks"]["ar_rank"] for r in rows if r["ranks"]["ar_rank"] is not None]

        assert len(cq_ranks) == len(set(cq_ranks)), f"duplicate cq_rank in {scale_id}"
        assert len(ar_ranks) == len(set(ar_ranks)), f"duplicate ar_rank in {scale_id}"

        assert all(isinstance(x, int) and x >= 1 for x in cq_ranks)
        assert all(isinstance(x, int) and x >= 1 for x in ar_ranks)


def test_coordination_matrix_recommendations_reference_existing_methods() -> None:
    """Recommendations ops_first, sec_first, balanced must reference method_id present in rows for that scale."""
    root = _repo_root()
    fixture = root / "tests" / "fixtures" / "coordination_matrix_fixture.v0.1.json"
    if not fixture.exists():
        pytest.skip("coordination matrix fixture not found")
    m = _load_json(fixture)

    methods_by_scale: dict[str, set[str]] = {}
    for r in m["rows"]:
        methods_by_scale.setdefault(r["scale_id"], set()).add(r["method_id"])

    for rec in m["recommendations"]:
        scale_id = rec["scale_id"]
        valid = methods_by_scale.get(scale_id, set())

        for slot in ["ops_first", "sec_first", "balanced"]:
            mid = rec[slot]["method_id"]
            assert (mid is None) or (
                mid in valid
            ), f"{slot} references unknown method {mid} for scale {scale_id}"
