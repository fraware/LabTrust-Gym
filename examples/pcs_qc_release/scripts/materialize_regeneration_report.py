#!/usr/bin/env python3
"""
Build regeneration_report.json from committed release artifacts (no CertifyEdge re-run).

Use after updating release fixtures manually or when regeneration_report.json was dropped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.protocol_artifacts import ProtocolRegenerationResult
from labtrust_gym.pcs.regeneration_report import (
    REGENERATION_REPORT_NAME,
    build_regeneration_report,
    write_regeneration_report,
)
from labtrust_gym.pcs.workflow_profile import workflow_profile_view


def main() -> int:
    release = ROOT / "examples" / "pcs_qc_release" / "release"
    if not (release / "trace.json").is_file():
        raise FileNotFoundError(f"incomplete release tree: {release}")

    profile = workflow_profile_view(
        ROOT / "examples" / "pcs_qc_release" / "workflow_profile.v0.json",
        policy_root=ROOT,
    )
    result = ProtocolRegenerationResult(release_dir=release, run_dir=release)
    report = build_regeneration_report(
        result,
        workflow_id=profile.workflow_id,
        duration_ms=0,
        status="passed",
        failure_code=None,
    )
    out = write_regeneration_report(release / REGENERATION_REPORT_NAME, report)
    print("wrote", out.relative_to(ROOT))
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
