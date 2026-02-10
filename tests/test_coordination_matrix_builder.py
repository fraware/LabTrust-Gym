"""Tests for coordination matrix builder: schema, determinism, snapshot, live-only."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from labtrust_gym.policy.loader import load_json, validate_against_schema
from labtrust_gym.studies.coordination_matrix_builder import build_coordination_matrix


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _fixture_run_dir() -> Path:
    return (
        Path(__file__).resolve().parent
        / "fixtures"
        / "coordination_matrix_run_fixture"
    )


def _schema_path() -> Path:
    return (
        _repo_root()
        / "policy"
        / "schemas"
        / "coordination_matrix.v0.1.schema.json"
    )


# Fixed timestamp for deterministic and snapshot tests.
FIXED_GENERATED_AT = "2026-02-08T00:00:00Z"


@pytest.fixture
def run_fixture_dir() -> Path:
    """Path to coordination_matrix_run_fixture; skip if missing."""
    d = _fixture_run_dir()
    if not (d / "summary_coord.csv").exists():
        pytest.skip("coordination_matrix_run_fixture not present")
    return d


# --- 5A) Schema validity test ---


def test_builder_output_validates_against_schema(run_fixture_dir: Path) -> None:
    """Run builder on run_fixture; validate output against matrix v0.1 schema."""
    schema_path = _schema_path()
    if not schema_path.exists():
        pytest.skip("coordination_matrix.v0.1.schema.json not found")

    out_path = run_fixture_dir / "coordination_matrix.v0.1.json"
    matrix = build_coordination_matrix(run_fixture_dir, out_path, strict=True)

    schema = load_json(schema_path)
    validate_against_schema(matrix, schema, out_path)


# --- 5B) Determinism test ---


def test_builder_determinism_identical_output(run_fixture_dir: Path) -> None:
    """Run builder twice with fixed time; assert JSON bytes / sha256 identical."""
    schema_path = _schema_path()
    if not schema_path.exists():
        pytest.skip("coordination_matrix.v0.1.schema.json not found")

    from datetime import datetime, timezone

    fixed_dt = datetime(2026, 2, 8, 0, 0, 0, tzinfo=timezone.utc)
    builder_dt = "labtrust_gym.studies.coordination_matrix_builder.datetime"

    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "matrix1.json"
        out2 = Path(tmp) / "matrix2.json"

        with patch(builder_dt) as mock_dt:
            mock_dt.now.return_value = fixed_dt
            mock_dt.side_effect = None
            build_coordination_matrix(run_fixture_dir, out1, strict=True)
        with patch(builder_dt) as mock_dt:
            mock_dt.now.return_value = fixed_dt
            mock_dt.side_effect = None
            build_coordination_matrix(run_fixture_dir, out2, strict=True)

        bytes1 = out1.read_bytes()
        bytes2 = out2.read_bytes()
        assert bytes1 == bytes2, "Two runs must produce identical JSON bytes"

        h1 = hashlib.sha256(bytes1).hexdigest()
        h2 = hashlib.sha256(bytes2).hexdigest()
        assert h1 == h2


# --- 5C) Snapshot test ---


def test_builder_output_matches_expected_fixture(run_fixture_dir: Path) -> None:
    """Builder output equals coordination_matrix_expected_output.v0.1.json."""
    expected_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "coordination_matrix_expected_output.v0.1.json"
    )
    if not expected_path.exists():
        pytest.skip("coordination_matrix_expected_output.v0.1.json not found")

    from datetime import datetime, timezone

    fixed_dt = datetime(2026, 2, 8, 0, 0, 0, tzinfo=timezone.utc)
    builder_dt = "labtrust_gym.studies.coordination_matrix_builder.datetime"

    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "coordination_matrix.v0.1.json"
        with patch(builder_dt) as mock_dt:
            mock_dt.now.return_value = fixed_dt
            mock_dt.side_effect = None
            build_coordination_matrix(run_fixture_dir, out_path, strict=True)

        actual = json.loads(out_path.read_text(encoding="utf-8"))
        expected = json.loads(expected_path.read_text(encoding="utf-8"))

        assert actual == expected, (
            "Builder output must match expected fixture exactly. "
            "Update tests/fixtures/coordination_matrix_expected_output.v0.1.json "
            "if the contract changed."
        )


# --- 5D) Live-only enforcement test ---


def test_builder_raises_when_pipeline_mode_not_llm_live(
    run_fixture_dir: Path,
) -> None:
    """Same as run_fixture but pipeline_mode=deterministic; builder must raise."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "deterministic_run"
        shutil.copytree(run_fixture_dir, tmp_path)
        metadata = tmp_path / "metadata.json"
        metadata.write_text(
            '{"pipeline_mode": "deterministic"}', encoding="utf-8"
        )

        out_path = tmp_path / "coordination_matrix.v0.1.json"
        with pytest.raises(ValueError) as exc_info:
            build_coordination_matrix(tmp_path, out_path, strict=True)

        msg = str(exc_info.value)
        assert "llm_live" in msg or "out of scope" in msg.lower()
