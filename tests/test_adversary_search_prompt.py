"""
Tests for the optional adversary search (prompt-space) script.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_adversary_search_prompt_output_structure_and_outcomes(tmp_path: Path) -> None:
    """Run script with --budget 3 --seed 42; assert JSON shape and outcomes."""
    root = _repo_root()
    script = root / "scripts" / "run_adversary_search_prompt.py"
    if not script.exists():
        pytest.skip("scripts/run_adversary_search_prompt.py not found")
    out_json = tmp_path / "out.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--budget",
            "3",
            "--seed",
            "42",
            "--out",
            str(out_json),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr!r} stdout: {proc.stdout!r}"  # noqa: E501
    assert out_json.exists()
    with open(out_json, encoding="utf-8") as f:
        data = json.load(f)
    assert "version" in data
    assert "policy_root" in data
    assert data["seed"] == 42
    assert data["budget"] == 3
    assert data["candidates_tried"] <= 3
    assert "results" in data
    assert len(data["results"]) <= 3
    for item in data["results"]:
        assert item["outcome"] in ("blocked", "accepted")
        assert "payload_preview" in item


def test_adversary_search_prompt_deterministic(tmp_path: Path) -> None:
    """Same seed and budget produce identical results."""
    root = _repo_root()
    script = root / "scripts" / "run_adversary_search_prompt.py"
    if not script.exists():
        pytest.skip("scripts/run_adversary_search_prompt.py not found")
    out1 = tmp_path / "out1.json"
    out2 = tmp_path / "out2.json"
    for out_path in (out1, out2):
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--budget",
                "3",
                "--seed",
                "42",
                "--out",
                str(out_path),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0
    with open(out1, encoding="utf-8") as f:
        data1 = json.load(f)
    with open(out2, encoding="utf-8") as f:
        data2 = json.load(f)
    assert data1["results"] == data2["results"]


def test_adversary_search_prompt_budget_one_no_crash(tmp_path: Path) -> None:
    """Run with --budget 1; assert report has candidates_tried and results list; no crash."""
    root = _repo_root()
    script = root / "scripts" / "run_adversary_search_prompt.py"
    if not script.exists():
        pytest.skip("scripts/run_adversary_search_prompt.py not found")
    out_json = tmp_path / "out_b1.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--budget",
            "1",
            "--seed",
            "42",
            "--out",
            str(out_json),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr!r}"
    assert out_json.exists()
    with open(out_json, encoding="utf-8") as f:
        data = json.load(f)
    assert "candidates_tried" in data
    assert "results" in data
    assert isinstance(data["results"], list)


def test_adversary_search_action_output_shape(tmp_path: Path) -> None:
    """Optional action-space script: run with budget 1, assert output shape."""
    root = _repo_root()
    script = root / "scripts" / "run_adversary_search_action.py"
    if not script.exists():
        pytest.skip("scripts/run_adversary_search_action.py not found")
    out_json = tmp_path / "action_out.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--budget",
            "1",
            "--seed",
            "42",
            "--out",
            str(out_json),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr!r}"
    assert out_json.exists()
    with open(out_json, encoding="utf-8") as f:
        data = json.load(f)
    assert "version" in data
    assert "policy_root" in data
    assert "candidates_tried" in data
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) >= 1
    for item in data["results"]:
        assert item["outcome"] in ("blocked", "accepted")
        assert "payload_preview" in item
