#!/usr/bin/env python3
"""CI: validate failure_case_manifest.json for every committed gallery case."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.failure_case_manifest import FAILURE_CASE_MANIFEST_NAME, load_failure_case_manifest

GALLERY = ROOT / "examples" / "pcs_qc_release" / "failures"


def main() -> int:
    profile_path = ROOT / "examples" / "pcs_qc_release" / "workflow_profile.v0.json"
    workflow_id = json.loads(profile_path.read_text(encoding="utf-8"))["workflow_id"]
    index_path = GALLERY / "gallery_index.json"
    if not index_path.is_file():
        raise FileNotFoundError(f"missing {index_path}")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    case_ids = {c["case_id"] for c in index.get("cases", [])}

    for case_id in sorted(case_ids):
        case_dir = GALLERY / case_id
        manifest_path = case_dir / FAILURE_CASE_MANIFEST_NAME
        if not manifest_path.is_file():
            raise FileNotFoundError(f"{case_id}: missing {FAILURE_CASE_MANIFEST_NAME}")
        doc = load_failure_case_manifest(manifest_path)
        if doc["failure_case_id"] != case_id:
            raise ValueError(f"{case_id}: failure_case_id mismatch")
        if doc["workflow_id"] != workflow_id:
            raise ValueError(f"{case_id}: workflow_id mismatch")
        artifacts_dir = case_dir / "artifacts"
        on_disk = sorted(p.name for p in artifacts_dir.iterdir() if p.is_file()) if artifacts_dir.is_dir() else []
        for name in doc["artifacts"]:
            if name not in on_disk:
                raise FileNotFoundError(f"{case_id}: manifest lists missing artifact {name}")
        print("OK", case_id, doc["expected_failure_code"])

    print("failure manifest validation OK", len(case_ids), "cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
