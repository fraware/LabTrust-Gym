#!/usr/bin/env python3
"""Generate committed Lean boundary failure-gallery cases."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.failure_gallery import build_single_failure_case

CASES = (
    "lean_trace_hash_mismatch",
    "lean_rejected_certificate",
    "lean_stale_certificate",
    "lean_signed_hash_mismatch",
)


def main() -> int:
    release = ROOT / "examples" / "pcs_qc_release" / "release"
    gallery = ROOT / "examples" / "pcs_qc_release" / "failures"
    for case_id in CASES:
        build_single_failure_case(
            case_id,
            gallery / case_id,
            policy_root=ROOT,
            release_dir=release,
        )
        print("OK", case_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
