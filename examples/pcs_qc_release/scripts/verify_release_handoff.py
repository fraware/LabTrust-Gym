#!/usr/bin/env python3
"""Verify examples/pcs_qc_release/release/ handoff for pcs-core promotion (exit 0/1)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.release_fixtures import release_dir
from labtrust_gym.pcs.release_handoff import verify_release_handoff


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=None,
        help="Release fixture directory (default: examples/pcs_qc_release/release)",
    )
    args = parser.parse_args()
    target = args.release_dir or release_dir()
    checks = verify_release_handoff(target)
    for label in checks:
        print("OK", label)
    print(f"release handoff verification OK ({len(checks)} checks, {target})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
