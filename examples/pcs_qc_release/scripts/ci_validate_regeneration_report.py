#!/usr/bin/env python3
"""CI: validate committed regeneration_report.json (pcs-bench contract)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.regeneration_report import (
    REGENERATION_REPORT_NAME,
    assert_regeneration_report_valid,
)


def main() -> int:
    release = ROOT / "examples" / "pcs_qc_release" / "release"
    report_path = release / REGENERATION_REPORT_NAME
    if not report_path.is_file():
        raise FileNotFoundError(
            f"missing {REGENERATION_REPORT_NAME}; run regenerate-release-protocol "
            f"or examples/pcs_qc_release/scripts/materialize_regeneration_report.py"
        )

    doc = json.loads(report_path.read_text(encoding="utf-8"))
    assert_regeneration_report_valid(
        doc,
        release_dir=release,
        expect_status="passed",
        policy_root=ROOT,
    )

    profile_path = release / "workflow_profile.v0.json"
    if profile_path.is_file():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if doc["workflow_id"] != profile.get("workflow_id"):
            raise ValueError("workflow_id mismatch vs workflow_profile.v0.json")

    print(f"OK {REGENERATION_REPORT_NAME}")
    print("OK workflow_id", doc["workflow_id"])
    print("OK artifacts_written", len(doc["artifacts_written"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
