#!/usr/bin/env python3
"""CI: validate committed examples/pcs_qc_release/release/ (pcs-core + LabTrust rules)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.release_fixtures import release_dir, validate_release_fixtures
from labtrust_gym.pcs.status_policy import check_release_status_policy
from labtrust_gym.pcs.sync_pcs_core_rc import pcs_core_labtrust_release_dir
from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol


def main() -> int:
    release = release_dir()
    names = validate_release_fixtures(release)
    for name in names:
        print("OK", name)

    status = check_release_status_policy(release)
    assert status["status"] == "passed"
    for label in status["checks"]:
        print("OK status_policy", label)

    for artifact in (
        "runtime_receipt.json",
        "trace_certificate.json",
        "science_claim_bundle.pending.json",
        "science_claim_bundle.certified.json",
        "handoff_to_certifyedge.json",
        "handoff_to_pf.json",
    ):
        path = release / artifact
        subprocess.run(["pcs", "validate", str(path)], check=True, cwd=ROOT)
        print("OK pcs validate", artifact)

    for artifact in ("handoff_to_certifyedge.json", "handoff_to_pf.json"):
        path = release / artifact
        subprocess.run(
            ["pcs", "registry", "check-artifact", str(path)],
            check=True,
            cwd=ROOT,
        )
        print("OK pcs registry check-artifact", artifact)

    fragment = release / "labtrust_release_fragment.json"
    if not fragment.is_file():
        raise FileNotFoundError(f"missing {fragment.name}")
    subprocess.run(["pcs", "validate", str(fragment)], check=True, cwd=ROOT)
    subprocess.run(
        ["pcs", "registry", "check-artifact", str(fragment)],
        check=True,
        cwd=ROOT,
    )
    print("OK pcs validate + registry labtrust_release_fragment.json")

    try:
        canonical = pcs_core_labtrust_release_dir(ROOT)
        for label in verify_release_protocol(release, pcs_core=canonical):
            print("OK protocol", label)
    except FileNotFoundError as exc:
        print("SKIP verify_release_protocol pcs-core:", exc)

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
    verify_cmd = [
        sys.executable,
        str(ROOT / "examples/pcs_qc_release/scripts/verify_release_handoff.py"),
        "--release",
        str(release),
    ]
    try:
        canonical = pcs_core_labtrust_release_dir(ROOT)
        verify_cmd.extend(["--pcs-core", str(canonical)])
    except FileNotFoundError as exc:
        print("SKIP pcs-core RC sync gate:", exc)
    subprocess.run(verify_cmd, check=True, cwd=ROOT)
    print("PCS release fixture validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
