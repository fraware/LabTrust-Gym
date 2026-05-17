#!/usr/bin/env python3
"""Write release/manifest.json with real git provenance (called from generate_release_candidate)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import json

from labtrust_gym.pcs.release_handoff import build_canonical_release_manifest, build_pf_handoff
from labtrust_gym.pcs.release_run import RELEASE_HANDOFF_MANIFEST_NAME


def main() -> int:
    release = Path(os.environ.get("PCS_RELEASE_DIR", ROOT / "examples/pcs_qc_release/release"))
    handoff_manifest_path = release / "handoff" / RELEASE_HANDOFF_MANIFEST_NAME
    if not handoff_manifest_path.is_file():
        handoff_manifest_path = release / RELEASE_HANDOFF_MANIFEST_NAME
    handoff_manifest = json.loads(handoff_manifest_path.read_text(encoding="utf-8"))
    manifest = build_canonical_release_manifest(
        release,
        handoff_manifest,
        generator=os.environ.get("PCS_MANIFEST_GENERATOR", "write_release_manifest.py"),
        certifyedge_bin=os.environ.get("CERTIFYEDGE_BIN", "certifyedge"),
        certifyedge_spec=os.environ.get("CERTIFYEDGE_SPEC", ""),
    )
    build_pf_handoff(release, manifest)
    print("OK manifest.json")
    print("OK pf_handoff.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
