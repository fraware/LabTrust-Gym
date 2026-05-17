"""PCS integrity and validate-pcs coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt
from labtrust_gym.pcs.validate import PcsValidationError, validate_run_dir

pytest.importorskip("pcs_core")


def test_validate_run_dir_valid(valid_run: Path) -> None:
    export_runtime_receipt(valid_run, valid_run / "pcs" / "receipt.json")
    export_pcs_bundle(valid_run, valid_run / "pcs" / "pending.json")
    validate_run_dir(valid_run)


def test_validate_run_dir_detects_trace_hash_tamper(valid_run: Path) -> None:
    trace = json.loads((valid_run / "trace.json").read_text(encoding="utf-8"))
    trace["trace_hash"] = "sha256:" + "f" * 64
    (valid_run / "trace.json").write_text(json.dumps(trace) + "\n", encoding="utf-8")
    with pytest.raises(PcsValidationError):
        validate_run_dir(valid_run)
