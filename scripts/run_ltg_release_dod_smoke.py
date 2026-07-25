#!/usr/bin/env python3
"""LTG-PR9 DoD smoke entrypoint (CI-friendly).

Runs the same checks as tests/test_ltg_benchmark_release_dod.py without requiring
heavy reproduce / official-pack. Exit 0 on success.

Usage (from repo root):
  python scripts/run_ltg_release_dod_smoke.py
  pytest -q tests/test_ltg_benchmark_release_dod.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    from labtrust_gym.policy.independent_review import (
        scientifically_reviewed_claim_allowed,
        validate_independent_review_gate,
    )
    from labtrust_gym.policy.validate import validate_policy

    print("LTG-PR9 DoD smoke (engineering benchmark; claim_allowed must be false)")

    docs = (
        "docs/benchmarks/scientific_credibility.md",
        "docs/benchmarks/release_runbook.md",
        "docs/benchmarks/non_claims_freeze.md",
        "benchmarks/releases/labtrust-benchmark-v0.2-candidate/NOTES.md",
        "benchmarks/releases/labtrust-benchmark-v0.2-candidate/release_manifest.json",
        "benchmarks/external_integrations/pinned_release.v1.json",
    )
    for rel in docs:
        if not (ROOT / rel).is_file():
            _fail(f"missing {rel}")
    print("OK docs + pin + candidate manifest present")

    errors = validate_policy(ROOT)
    if errors:
        _fail("validate_policy:\n" + "\n".join(errors))
    print("OK validate_policy")

    review_errors = validate_independent_review_gate(ROOT)
    if review_errors:
        _fail("independent review gate:\n" + "\n".join(review_errors))
    if scientifically_reviewed_claim_allowed(ROOT):
        _fail("scientifically_reviewed_claim_allowed must be false for this candidate")
    print("OK independent review gate (claim_allowed=false)")

    import labtrust_gym.export.reconstruction as recon
    import labtrust_gym.export.receipts as receipts
    import labtrust_gym.export.verify as verify

    for name, obj in (
        ("build_reconstruction_block", recon.build_reconstruction_block),
        ("write_evidence_bundle", receipts.write_evidence_bundle),
        ("verify_bundle", verify.verify_bundle),
    ):
        if not callable(obj):
            _fail(f"{name} not importable/callable")
    print("OK reconstruction/export helpers")

    manifest = json.loads(
        (ROOT / "benchmarks/releases/labtrust-benchmark-v0.2-candidate/release_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    if manifest.get("scientifically_reviewed") is not False:
        _fail("candidate manifest scientifically_reviewed must be false")
    if manifest.get("scientifically_reviewed_claim_allowed") is not False:
        _fail("candidate manifest scientifically_reviewed_claim_allowed must be false")
    print("OK candidate claim posture")

    print(
        "PASS - engineering benchmark DoD smoke green. "
        "Full reproduce/verify-release: docs/benchmarks/release_runbook.md"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
