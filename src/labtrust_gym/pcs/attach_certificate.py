"""Attach CertifyEdge TraceCertificate.v0 to a pending ScienceClaimBundle."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def attach_trace_certificate(
    bundle: dict[str, Any],
    certificate: dict[str, Any],
) -> dict[str, Any]:
    """Return a new certified bundle with certificate inserted and refs updated."""
    out = copy.deepcopy(bundle)
    receipt = out["runtime_receipts"][0]
    trace_hash = receipt["trace_hash"]
    cert = dict(certificate)
    cert.setdefault("schema_version", "v0")
    if cert.get("trace_hash") != trace_hash:
        raise ValueError(f"certificate trace_hash {cert.get('trace_hash')!r} != receipt {trace_hash!r}")
    cert_id = cert["certificate_id"]
    from_status = out["claim_artifact"].get("status", "RuntimeObserved")
    from labtrust_gym.pcs.status_transitions import (
        CERTIFIED_CLAIM_STATUS,
        assert_claim_status_transition,
        assert_pending_bundle_claim_status,
        mark_bundle_stale_if_trace_diverged,
    )

    assert_pending_bundle_claim_status(out)
    assert_claim_status_transition(from_status, CERTIFIED_CLAIM_STATUS)

    out["certificates"] = [cert]
    mark_bundle_stale_if_trace_diverged(out, context="attach-certificate")
    claim = out["claim_artifact"]
    claim["certificate_refs"] = [cert_id]
    claim["status"] = CERTIFIED_CLAIM_STATUS
    evidence = out["evidence_bundle"]
    evidence["certificate_refs"] = [cert_id]
    evidence["artifact_hashes"][cert_id] = cert["signature_or_digest"]
    from labtrust_gym.pcs.provenance import with_signature
    from labtrust_gym.pcs.schema_version import assert_science_claim_bundle_versions

    base = {k: v for k, v in out.items() if k != "signature_or_digest"}
    signed = with_signature(base)
    assert_science_claim_bundle_versions(signed)
    from labtrust_gym.pcs.status_transitions import assert_certified_bundle_claim_status

    assert_certified_bundle_claim_status(signed)
    return signed


def attach_certificate_files(
    bundle_path: Path,
    certificate_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    bundle = load_json(bundle_path)
    certificate = load_json(certificate_path)
    certified = attach_trace_certificate(bundle, certificate)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(certified, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return certified
