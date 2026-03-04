"""
R-TOOL-005 (Function call misparameterization): fuzzing validate_tool_args.

Invalid args (wrong type, out-of-range, extra keys, missing required) must be
rejected with TOOL_ARG_SCHEMA_FAIL or TOOL_ARG_RANGE_FAIL.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.tools.arg_validation import (
    TOOL_ARG_RANGE_FAIL,
    TOOL_ARG_SCHEMA_FAIL,
    validate_tool_args,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def registry(repo_root: Path) -> dict:
    return {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {
                    "tool_id": "read_lims_v1",
                    "arg_schema_ref": "tool_args/read_lims_v1.args.v0.1.schema.json",
                },
            ],
        },
    }


def test_missing_required_rejected(registry: dict, repo_root: Path) -> None:
    """Missing required accession_id -> TOOL_ARG_SCHEMA_FAIL."""
    ok, reason, _ = validate_tool_args("read_lims_v1", {}, registry, repo_root)
    assert ok is False
    assert reason == TOOL_ARG_SCHEMA_FAIL


def test_wrong_type_rejected(registry: dict, repo_root: Path) -> None:
    """accession_id as int instead of string -> TOOL_ARG_SCHEMA_FAIL."""
    ok, reason, _ = validate_tool_args("read_lims_v1", {"accession_id": 123}, registry, repo_root)
    assert ok is False
    assert reason == TOOL_ARG_SCHEMA_FAIL


def test_out_of_range_rejected(registry: dict, repo_root: Path) -> None:
    """limit outside [1,1000] -> TOOL_ARG_RANGE_FAIL."""
    ok, reason, _ = validate_tool_args(
        "read_lims_v1",
        {"accession_id": "ACC001", "limit": 0},
        registry,
        repo_root,
    )
    assert ok is False
    assert reason == TOOL_ARG_RANGE_FAIL


def test_extra_property_rejected(registry: dict, repo_root: Path) -> None:
    """additionalProperties: false -> extra key -> TOOL_ARG_SCHEMA_FAIL."""
    ok, reason, _ = validate_tool_args(
        "read_lims_v1",
        {"accession_id": "ACC001", "malicious_key": "x"},
        registry,
        repo_root,
    )
    assert ok is False
    assert reason == TOOL_ARG_SCHEMA_FAIL


def test_valid_args_accepted(registry: dict, repo_root: Path) -> None:
    """Valid args pass."""
    ok, reason, _ = validate_tool_args(
        "read_lims_v1",
        {"accession_id": "ACC001"},
        registry,
        repo_root,
    )
    assert ok is True
    assert reason is None
