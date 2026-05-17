"""RuntimeReceipt export validates and matches trace."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.export import export_runtime_receipt
from labtrust_gym.pcs.validate import validate_pcs_artifact


def test_runtime_receipt_validates_and_trace_hash_matches(valid_run: Path, tmp_path: Path) -> None:
    out = tmp_path / "runtime_receipt.json"
    receipt = export_runtime_receipt(valid_run, out)
    trace = json.loads((valid_run / "trace.json").read_text(encoding="utf-8"))
    assert receipt["trace_hash"] == trace["trace_hash"]
    assert receipt["status"] == "RuntimeObserved"
    assert receipt["run_outcome"] == "passed"
    assert receipt["final_reason_code"] == "ok"
    assert receipt["released"] is True
    assert receipt["schema_version"] == "v0"
    validate_pcs_artifact(receipt)
