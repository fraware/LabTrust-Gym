#!/usr/bin/env python3
"""Verify examples/pcs_qc_release/release/ handoff and pcs-core RC sync gate (exit 0/1)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.release_fixtures import release_dir
from labtrust_gym.pcs.sync_pcs_core_rc import (
    pcs_core_labtrust_release_dir,
    verify_release_sync_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify LabTrust release/ handoff integrity and, with --pcs-core, "
            "compare artifact hashes and commits to pcs-core/examples/labtrust-release/."
        )
    )
    parser.add_argument(
        "--release",
        "--release-dir",
        dest="release_dir",
        type=Path,
        default=None,
        help="LabTrust release fixture directory (default: examples/pcs_qc_release/release)",
    )
    parser.add_argument(
        "--pcs-core",
        type=Path,
        default=None,
        help="pcs-core canonical RC directory (e.g. ../pcs-core/examples/labtrust-release)",
    )
    args = parser.parse_args()
    target = (args.release_dir or release_dir()).resolve()

    canonical: Path | None = None
    if args.pcs_core is not None:
        canonical = args.pcs_core.resolve()
        if not canonical.is_dir():
            raise SystemExit(f"pcs-core canonical path not found: {canonical}")
    else:
        try:
            canonical = pcs_core_labtrust_release_dir(ROOT)
        except FileNotFoundError:
            canonical = None

    checks = verify_release_sync_gate(target, canonical)
    for label in checks:
        print("OK", label)

    if canonical is not None:
        print(f"pcs-core RC sync gate OK ({canonical})")
    print(f"release handoff verification OK ({len(checks)} checks, {target})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
