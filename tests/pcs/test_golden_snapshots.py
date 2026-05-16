"""Golden trace and bundle snapshots for PCS QC-release demo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.export import export_runtime_receipt, export_trace

EXPECTED = get_repo_root() / "examples" / "pcs_qc_release" / "expected"


@pytest.fixture
def expected_dir() -> Path:
    if not EXPECTED.is_dir():
        pytest.skip("expected/ snapshots not present")
    return EXPECTED


def test_valid_trace_matches_golden(tmp_path: Path, expected_dir: Path, repo_root: Path) -> None:
    run_dir = tmp_path / "run"
    run_demo("qc-release", out_dir=run_dir, policy_root=repo_root)
    out = tmp_path / "trace.json"
    trace = export_trace(run_dir, out)
    golden = json.loads((expected_dir / "valid_trace.json").read_text(encoding="utf-8"))
    assert trace["trace_hash"] == golden["trace_hash"]
    assert [e["action"] for e in trace["events"]] == [e["action"] for e in golden["events"]]


def test_valid_runtime_receipt_trace_hash(tmp_path: Path, expected_dir: Path, repo_root: Path) -> None:
    run_dir = tmp_path / "run"
    run_demo("qc-release", out_dir=run_dir, policy_root=repo_root)
    receipt = export_runtime_receipt(run_dir, tmp_path / "receipt.json", policy_root=repo_root)
    golden = json.loads((expected_dir / "valid_runtime_receipt.json").read_text(encoding="utf-8"))
    assert receipt["trace_hash"] == golden["trace_hash"]


def test_invalid_missing_qc_reason(tmp_path: Path, expected_dir: Path, repo_root: Path) -> None:
    run_dir = tmp_path / "run"
    run_demo("qc-release-invalid-missing-qc", out_dir=run_dir, policy_root=repo_root)
    golden = json.loads((expected_dir / "invalid_missing_qc_result.json").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["final_reason_code"] == golden["final_reason_code"] == "missing_qc"


def test_invalid_unauthorized_reason(tmp_path: Path, expected_dir: Path, repo_root: Path) -> None:
    run_dir = tmp_path / "run"
    run_demo("qc-release-invalid-unauthorized", out_dir=run_dir, policy_root=repo_root)
    golden = json.loads((expected_dir / "invalid_unauthorized_result.json").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["final_reason_code"] == golden["final_reason_code"] == "unauthorized_release"
