#!/usr/bin/env python3
"""Validate PCS v0.1 clean-chain artifact files (pcs-core + LabTrust rules)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.mock_certificate import is_mock_certificate
from labtrust_gym.pcs.release_fixtures import validate_release_fixtures
from labtrust_gym.pcs.schema_version import assert_no_legacy_pf_bundle_keys
from labtrust_gym.pcs.validate import (
    require_pcs_core,
    validate_runtime_receipt,
    validate_science_claim_bundle,
    validate_trace,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_labtrust_segment(work: Path) -> list[str]:
    require_pcs_core()
    from pcs_core.validate import validate_artifact

    ok: list[str] = []
    trace = _load(work / "trace.json")
    receipt = _load(work / "runtime_receipt.json")
    pending = _load(work / "science_claim_bundle.pending.json")

    validate_trace(trace)
    validate_runtime_receipt(receipt)
    validate_science_claim_bundle(pending)
    validate_artifact(receipt)
    validate_artifact(pending)
    assert_no_legacy_pf_bundle_keys(pending)

    th = receipt["trace_hash"]
    if trace["trace_hash"] != th:
        raise ValueError("trace.trace_hash != runtime_receipt.trace_hash")
    if pending["runtime_receipts"][0]["trace_hash"] != th:
        raise ValueError("pending bundle trace_hash mismatch")

    ok.extend(["trace.json", "runtime_receipt.json", "science_claim_bundle.pending.json"])
    return ok


def validate_through_certified(work: Path) -> list[str]:
    ok = validate_labtrust_segment(work)
    require_pcs_core()
    from pcs_core.validate import validate_artifact

    cert = _load(work / "trace_certificate.json")
    certified = _load(work / "science_claim_bundle.certified.json")
    receipt = _load(work / "runtime_receipt.json")

    if is_mock_certificate(cert):
        raise ValueError("trace_certificate.json must be CertifyEdge output, not LabTrust mock digest")

    validate_artifact(cert)
    validate_science_claim_bundle(certified)
    validate_artifact(certified)
    assert_no_legacy_pf_bundle_keys(certified)

    th = receipt["trace_hash"]
    if cert["trace_hash"] != th:
        raise ValueError("certificate trace_hash != runtime_receipt.trace_hash")
    if certified["certificates"][0]["trace_hash"] != th:
        raise ValueError("certified bundle certificate trace_hash mismatch")

    ok.extend(["trace_certificate.json", "science_claim_bundle.certified.json"])
    return ok


def validate_full_chain(work: Path) -> list[str]:
    ok = validate_through_certified(work)
    require_pcs_core()
    from pcs_core.validate import validate_artifact

    for name in ("verification_result.json", "signed_science_claim_bundle.json"):
        path = work / name
        if not path.is_file():
            raise FileNotFoundError(f"missing {name}")
        doc = _load(path)
        validate_artifact(doc)
        ok.append(name)

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT, help="Chain work directory (repo root by default)")
    parser.add_argument(
        "--stage",
        choices=("labtrust", "certified", "full"),
        default="full",
        help="How much of the chain to validate",
    )
    args = parser.parse_args()
    work = args.work.resolve()

    if args.stage == "labtrust":
        names = validate_labtrust_segment(work)
    elif args.stage == "certified":
        names = validate_through_certified(work)
    else:
        names = validate_full_chain(work)

    for name in names:
        print("OK", name)
    print(f"PCS v0.1 chain validation OK ({args.stage}, {len(names)} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
