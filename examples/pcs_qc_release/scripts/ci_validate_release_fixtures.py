#!/usr/bin/env python3
"""CI: validate committed examples/pcs_qc_release/release/ (pcs-core + LabTrust rules)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.release_fixtures import release_dir, validate_release_fixtures
from labtrust_gym.pcs.release_handoff import verify_release_handoff


def main() -> int:
    release = release_dir()
    names = validate_release_fixtures(release)
    for name in names:
        print("OK", name)

    for artifact in (
        "runtime_receipt.json",
        "trace_certificate.json",
        "science_claim_bundle.pending.json",
        "science_claim_bundle.certified.json",
    ):
        path = release / artifact
        subprocess.run(["pcs", "validate", str(path)], check=True, cwd=ROOT)
        print("OK pcs validate", artifact)

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/pcs_qc_release/scripts/verify_pcs_v01_chain.py"),
            "--work",
            str(release),
            "--stage",
            "certified",
        ],
        check=True,
        cwd=ROOT,
    )
    for label in verify_release_handoff(release):
        print("OK handoff", label)

    subprocess.run(
        [sys.executable, str(ROOT / "examples/pcs_qc_release/scripts/verify_release_handoff.py")],
        check=True,
        cwd=ROOT,
    )
    try:
        from labtrust_gym.pcs.sync_pcs_core_rc import assert_release_matches_pcs_core_rc

        assert_release_matches_pcs_core_rc(release)
        print("OK pcs-core RC chain identity")
    except FileNotFoundError as exc:
        print("SKIP pcs-core RC compare:", exc)
    print("PCS release fixture validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
