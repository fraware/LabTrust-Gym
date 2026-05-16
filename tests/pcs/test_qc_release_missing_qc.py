"""Missing-QC workflow rejects release_sample before QC."""

from __future__ import annotations

import json
from pathlib import Path


def test_release_rejected_missing_qc(missing_qc_run: Path) -> None:
    meta = json.loads((missing_qc_run / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["released"] is False
    trace = json.loads((missing_qc_run / "trace.json").read_text(encoding="utf-8"))
    release_events = [e for e in trace["events"] if e["action"] == "release_sample"]
    assert len(release_events) == 1
    assert release_events[0]["policy_decision"] == "deny"
    assert release_events[0]["reason_code"] == "missing_qc"
