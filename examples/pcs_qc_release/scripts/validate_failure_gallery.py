#!/usr/bin/env python3
"""CI: verify every failure-gallery case fails its expected check."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.failure_gallery import verify_failure_gallery


def main() -> int:
    gallery = ROOT / "examples" / "pcs_qc_release" / "failures"
    checks = verify_failure_gallery(gallery, policy_root=ROOT)
    for label in checks:
        print("OK", label)
    print("failure gallery validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
