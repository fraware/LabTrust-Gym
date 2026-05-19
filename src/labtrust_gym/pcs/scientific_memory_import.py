"""Scientific Memory import readiness checks on PCS release trees."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.formalization import DOWNSTREAM_PF_ARTIFACTS
from labtrust_gym.pcs.release_run import certified_bundle_ids, validate_certificate_id_chain

SCIENTIFIC_MEMORY_IMPORT_CHECK = "scientific_memory_import.claim_id_alignment"
SCIENTIFIC_MEMORY_CLAIM_ID_MISMATCH = "SCIENTIFIC_MEMORY_CLAIM_ID_MISMATCH"

_FALLBACK_DOWNSTREAM_REL = Path(
    "examples/pcs_qc_release/failures/lean_signed_hash_mismatch/artifacts"
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def certified_claim_id(release_dir: Path) -> str:
    certified = _load_json(release_dir / "science_claim_bundle.certified.json")
    claim = certified.get("claim_artifact") or {}
    claim_id = claim.get("artifact_id")
    if not claim_id:
        raise ValueError("science_claim_bundle.certified.json missing claim_artifact.artifact_id")
    return str(claim_id)


def signed_claim_id(signed_doc: dict[str, Any]) -> str:
    bundle = signed_doc.get("science_claim_bundle", signed_doc)
    claim = bundle.get("claim_artifact") or {}
    claim_id = claim.get("artifact_id")
    if not claim_id:
        raise ValueError("signed_science_claim_bundle.json missing claim_artifact.artifact_id")
    return str(claim_id)


def align_downstream_pf_artifacts_to_release(
    release_dir: Path,
    dest_dir: Path,
    *,
    signed_doc: dict[str, Any] | None = None,
) -> None:
    """Rewrite PF downstream artifacts in ``dest_dir`` to match ``release_dir`` certificate chain."""
    release_dir = release_dir.resolve()
    dest_dir = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    certified = _load_json(release_dir / "science_claim_bundle.certified.json")
    _bundle_id, cert_id, trace_hash = certified_bundle_ids(certified)
    claim_id = certified_claim_id(release_dir)

    if signed_doc is None:
        signed_path = dest_dir / "signed_science_claim_bundle.json"
        if not signed_path.is_file():
            raise FileNotFoundError(f"missing {signed_path}")
        signed_doc = _load_json(signed_path)

    bundle = signed_doc.setdefault("science_claim_bundle", signed_doc)
    claim = bundle.setdefault("claim_artifact", {})
    claim["artifact_id"] = claim_id
    claim_refs = claim.setdefault("certificate_refs", [])
    if claim_refs:
        claim_refs[0] = cert_id
    for cert in bundle.get("certificates", []):
        cert["certificate_id"] = cert_id
        cert["trace_hash"] = trace_hash
    for receipt in bundle.get("runtime_receipts", []):
        receipt["trace_hash"] = trace_hash

    verification_path = dest_dir / "verification_result.json"
    if verification_path.is_file():
        verification = _load_json(verification_path)
        verified = verification.setdefault("verified_input", {})
        verified["certificate_id"] = cert_id
        verified["trace_hash"] = trace_hash
        for check in verification.get("checks", []):
            if check.get("check_id") == "evidence_refs_complete":
                details = check.setdefault("details", {})
                refs = details.setdefault("certificate_refs", [])
                if refs:
                    refs[0] = cert_id
                else:
                    details["certificate_refs"] = [cert_id]
        verification_path.write_text(
            json.dumps(verification, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    (dest_dir / "signed_science_claim_bundle.json").write_text(
        json.dumps(signed_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resolve_downstream_template(policy_root: Path) -> Path:
    from labtrust_gym.pcs.sync_pcs_core_rc import pcs_core_labtrust_release_dir

    try:
        canon = pcs_core_labtrust_release_dir(policy_root)
        if (canon / "signed_science_claim_bundle.json").is_file():
            return canon
    except FileNotFoundError:
        pass
    fallback = policy_root / _FALLBACK_DOWNSTREAM_REL
    if (fallback / "signed_science_claim_bundle.json").is_file():
        return fallback
    raise FileNotFoundError(
        "no signed_science_claim_bundle.json template; sync pcs-core RC or keep "
        "examples/pcs_qc_release/failures/lean_signed_hash_mismatch/artifacts/"
    )


def materialize_downstream_release_artifacts(
    release_dir: Path,
    *,
    policy_root: Path,
) -> list[str]:
    """Copy and align PF downstream artifacts into ``release_dir``."""
    release_dir = release_dir.resolve()
    template = resolve_downstream_template(policy_root)
    written: list[str] = []
    for name in DOWNSTREAM_PF_ARTIFACTS:
        src = template / name
        if not src.is_file():
            continue
        shutil.copy2(src, release_dir / name)
        written.append(name)
    if "signed_science_claim_bundle.json" in written:
        align_downstream_pf_artifacts_to_release(release_dir, release_dir)
        validate_certificate_id_chain(release_dir)
    return written


def assert_scientific_memory_import_alignment(release_dir: Path) -> None:
    """
    Raise when ``signed_science_claim_bundle.json`` claim_id does not match the certified bundle.

    Scientific Memory imports SignedScienceClaimBundle.v0; claim_id drift blocks import.
    """
    release_dir = release_dir.resolve()
    signed_path = release_dir / "signed_science_claim_bundle.json"
    if not signed_path.is_file():
        raise FileNotFoundError("missing signed_science_claim_bundle.json for Scientific Memory import")
    expected = certified_claim_id(release_dir)
    actual = signed_claim_id(_load_json(signed_path))
    if actual != expected:
        raise ValueError(
            f"{SCIENTIFIC_MEMORY_CLAIM_ID_MISMATCH}: signed claim_id {actual!r} != "
            f"certified claim_id {expected!r}"
        )
    validate_certificate_id_chain(release_dir)
