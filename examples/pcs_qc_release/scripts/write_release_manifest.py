#!/usr/bin/env python3
"""Write release/manifest.json with real git provenance (called from generate_release_candidate)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.manifest import build_release_manifest


def main() -> int:
    release = Path(os.environ.get("PCS_RELEASE_DIR", ROOT / "examples/pcs_qc_release/release"))
    build_release_manifest(
        release,
        generator=os.environ.get("PCS_MANIFEST_GENERATOR", "write_release_manifest.py"),
        certifyedge_bin=os.environ.get("CERTIFYEDGE_BIN", "certifyedge"),
        certifyedge_spec=os.environ.get("CERTIFYEDGE_SPEC", ""),
        certifyedge_root=Path(os.environ["CERTIFYEDGE_ROOT"]) if os.environ.get("CERTIFYEDGE_ROOT") else None,
        labtrust_root=ROOT,
    )
    print("OK manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
