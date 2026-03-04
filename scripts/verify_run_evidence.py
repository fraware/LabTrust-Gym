#!/usr/bin/env python3
"""
Verify run-dir evidence before using it for export-risk-register or release.

For each run dir: (1) discover EvidenceBundle.v0.1 under run_dir/receipts/ and run
verify_bundle on each; (2) if SECURITY/attack_results.json exists, verify its .sha256.
Exit 1 if any check fails. Used by run_required_bench_matrix.sh before export-risk-register.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root or scripts/
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from labtrust_gym.export.verify import (  # noqa: E402
    discover_evidence_bundles,
    verify_bundle,
    verify_security_attack_results_checksum,
)


def verify_one_run_dir(run_dir: Path, policy_root: Path) -> list[str]:
    """Run all evidence checks for one run dir. Returns list of error messages."""
    errors: list[str] = []
    run_dir = Path(run_dir)
    for bundle_path in discover_evidence_bundles(run_dir):
        passed, _report, bundle_errors = verify_bundle(
            bundle_path,
            policy_root=policy_root,
            allow_extra_files=False,
        )
        if not passed and bundle_errors:
            errors.append(f"verify-bundle {bundle_path}: {bundle_errors[0]}")
            errors.extend(bundle_errors[1:])
    sec_errors = verify_security_attack_results_checksum(run_dir)
    if sec_errors:
        errors.append(f"SECURITY checksum {run_dir}: {sec_errors[0]}")
        errors.extend(sec_errors[1:])
    return errors


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Verify run-dir evidence (bundles + SECURITY).")
    parser.add_argument("run_dirs", nargs="+", type=Path, help="Run directory/ies to verify")
    parser.add_argument("--policy-root", type=Path, default=_REPO_ROOT, help="Policy root for verify_bundle")
    args = parser.parse_args()
    policy_root = Path(args.policy_root)
    all_errors: list[str] = []
    for run_dir in args.run_dirs:
        if not run_dir.is_dir():
            all_errors.append(f"Not a directory: {run_dir}")
            continue
        all_errors.extend(verify_one_run_dir(run_dir, policy_root))
    if all_errors:
        for e in all_errors:
            print(e)
        print(f"Evidence verification failed ({len(all_errors)} error(s)).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
