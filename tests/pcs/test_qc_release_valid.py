"""Valid QC-release workflow reaches release_sample."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.trace import REQUIRED_ACTIONS


def test_valid_run_reaches_release(valid_run: Path) -> None:
    meta = json.loads((valid_run / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"
    assert meta["released"] is True
    assert meta["final_reason_code"] == "ok"
    trace = json.loads((valid_run / "trace.json").read_text(encoding="utf-8"))
    actions = [e["action"] for e in trace["events"]]
    assert actions[-1] == "release_sample"
    assert trace["events"][-1]["reason_code"] == "ok"
    for action in REQUIRED_ACTIONS:
        assert action in actions
