#!/usr/bin/env python3
"""
Normalize release fixture to LF and regenerate all manifest hashes.

Run before test_release_fixture_verify_release on CI so that RELEASE_MANIFEST
and receipt manifests match the files as checked out (LF). Use after checkout
in the release-fixture-verify workflow so the test passes regardless of
how the fixture was committed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _to_lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    release_dir = repo_root / "tests" / "fixtures" / "release_fixture_minimal"
    if len(sys.argv) > 1:
        release_dir = Path(sys.argv[1]).resolve()

    if not release_dir.is_dir():
        print(f"Release dir not found: {release_dir}", file=sys.stderr)
        return 1

    # 1. Normalize all .json and .jsonl to LF
    for p in release_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".json", ".jsonl"):
            raw = p.read_bytes()
            lf = _to_lf(raw)
            if lf != raw:
                p.write_bytes(lf)

    # 2. Update each receipt EvidenceBundle manifest.json
    receipts = release_dir / "receipts"
    if receipts.is_dir():
        for entry in sorted(receipts.iterdir()):
            if not entry.is_dir():
                continue
            bundle_dir = entry / "EvidenceBundle.v0.1"
            manifest_path = bundle_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            new_files = []
            for f in manifest.get("files", []):
                path_str = f.get("path")
                if path_str and (bundle_dir / path_str).exists():
                    new_files.append({"path": path_str, "sha256": _sha256(bundle_dir / path_str)})
                else:
                    new_files.append(f)
            manifest["files"] = new_files
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )

    # 3. Update top-level MANIFEST.v0.1.json
    manifest_path = release_dir / "MANIFEST.v0.1.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        new_files = []
        for entry in manifest.get("files", []):
            path_str = entry.get("path")
            if path_str:
                full = release_dir / path_str
                if full.exists():
                    new_files.append({"path": path_str, "sha256": _sha256(full)})
                else:
                    new_files.append(entry)
            else:
                new_files.append(entry)
        manifest["files"] = new_files
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

    # 4. Build RELEASE_MANIFEST.v0.1.json
    sys.path.insert(0, str(repo_root))
    from labtrust_gym.export.verify import build_release_manifest

    build_release_manifest(release_dir)
    print(f"Normalized and regenerated manifests in {release_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
