#!/usr/bin/env python3
"""Sync examples/pcs_qc_release/release/ from pcs-core/examples/labtrust-release/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.sync_pcs_core_rc import sync_release_from_pcs_core_rc


def main() -> int:
    target = sync_release_from_pcs_core_rc(generator="sync_release_from_pcs_core.py")
    print(f"OK synced release fixtures from pcs-core RC -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
