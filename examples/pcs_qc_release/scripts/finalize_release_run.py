#!/usr/bin/env python3
"""Write release-run manifests and atomically promote to examples/pcs_qc_release/release/."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.release_run import (  # noqa: E402
    promote_release_run_atomic,
    resolve_release_repo_commits,
    write_run_manifests,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT / "examples/pcs_qc_release/release-run",
        help="Completed release-run directory (handoff artifacts present)",
    )
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=ROOT / "examples/pcs_qc_release/release",
        help="Promotion target (release/ fixtures)",
    )
    parser.add_argument("--generator", default=os.environ.get("PCS_MANIFEST_GENERATOR", "finalize_release_run.py"))
    parser.add_argument("--handoff-id", default=os.environ.get("PCS_HANDOFF_ID", ""))
    parser.add_argument("--no-promote", action="store_true", help="Only write manifests into run-dir")
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    ce_root = Path(os.environ["CERTIFYEDGE_ROOT"]) if os.environ.get("CERTIFYEDGE_ROOT") else None

    require_pf = (run_dir / "signed_science_claim_bundle.json").is_file()
    require_sm = (run_dir / "scientific_memory_import_report.json").is_file()

    commits = resolve_release_repo_commits(
        ROOT,
        certifyedge_root=ce_root,
        require_pf=require_pf,
        require_sm=require_sm,
    )
    handoff_id = args.handoff_id.strip() or None
    write_run_manifests(run_dir, commits, generator=args.generator, handoff_id=handoff_id)
    print(f"OK {run_dir.name}/RELEASE_HANDOFF_MANIFEST.json")
    print(f"OK {run_dir.name}/handoff_for_pf.json")
    print(f"OK {run_dir.name}/RELEASE_FIXTURE_MANIFEST.json")

    if not args.no_promote:
        promote_release_run_atomic(
            run_dir,
            args.release_dir,
            generator=args.generator,
            certifyedge_bin=os.environ.get("CERTIFYEDGE_BIN", "certifyedge"),
            certifyedge_spec=os.environ.get("CERTIFYEDGE_SPEC", ""),
        )
        print(f"OK promoted release-run -> {args.release_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
