"""Trace export: fields, hash chain, determinism."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.export import export_trace
from labtrust_gym.pcs.trace import TRACE_EVENT_FIELDS, compute_trace_hash, verify_event_hash_chain


def test_trace_required_fields_and_hash_chain(valid_run: Path, tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    trace = export_trace(valid_run, out)
    for event in trace["events"]:
        for field in TRACE_EVENT_FIELDS:
            assert field in event
    assert verify_event_hash_chain(trace["events"]) == []
    assert trace["trace_hash"] == compute_trace_hash(
        trace["events"], run_id=trace["run_id"], sample_id=trace["sample_id"]
    )


def test_trace_hash_deterministic(repo_root: Path, tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    run_demo("qc-release", out_dir=a, policy_root=repo_root)
    run_demo("qc-release", out_dir=b, policy_root=repo_root)
    ta = json.loads((a / "trace.json").read_text(encoding="utf-8"))
    tb = json.loads((b / "trace.json").read_text(encoding="utf-8"))
    assert ta["trace_hash"] == tb["trace_hash"]
