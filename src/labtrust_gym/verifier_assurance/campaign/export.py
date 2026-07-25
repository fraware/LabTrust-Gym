"""Campaign PCS export, hidden-label exclusion, reconstruction (LT-VA-08)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from labtrust_gym.util.json_utils import canonical_json
from labtrust_gym.verifier_assurance.mutations.profiles import (
    enforce_production_prohibition_for_release,
    validate_mutation_profile,
)
from labtrust_gym.verifier_assurance.oracle.dual_oracle import deny_hidden_in_mapping

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"

REQUIRED_TREE = (
    "campaign_manifest.pcs.json",
    "environment_profile.json",
    "verifier_profiles",
    "trajectories",
    "snapshots",
    "reward_evidence",
    "verifier_results",
    "adjudications_or_commitments",
    "exploit_manifests",
    "counterfactual_branches",
    "assurance_report.pcs.json",
    "release_manifest.json",
)


class CampaignExportError(ValueError):
    """Fail-closed campaign export/reconstruction error."""


def _write_json(path: Path, doc: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dict(doc), indent=2, sort_keys=True) + "\n"
    # Use binary write so checksums are stable across Windows newline translation.
    data = text.encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _assert_no_hidden_labels(doc: Any, *, path: str) -> None:
    deny_hidden_in_mapping(doc, path=path)
    if isinstance(doc, Mapping):
        # Explicit: adjudications may appear only as commitments in public packs
        if doc.get("revealed") is True and doc.get("adjudication") is not None:
            raise CampaignExportError(f"hidden adjudication revealed in public artifact at {path}")


def export_campaign_pack(
    out_dir: Path | str,
    *,
    campaign_id: str,
    environment_profile: Mapping[str, Any],
    verifier_profiles: list[Mapping[str, Any]],
    trajectories: list[Mapping[str, Any]],
    snapshots: list[Mapping[str, Any]],
    reward_evidence: list[Mapping[str, Any]],
    verifier_results: list[Mapping[str, Any]],
    commitments: list[Mapping[str, Any]],
    exploit_manifests: list[Mapping[str, Any]],
    counterfactual_branches: list[Mapping[str, Any]],
    mutation_profiles: list[Mapping[str, Any]] | None = None,
    include_revealed_adjudications: bool = False,
) -> dict[str, Any]:
    """
    Write release-grade campaign pack. Active hidden labels excluded from public artifacts
    (commitments only) unless include_revealed_adjudications for private packs after freeze.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mutations = [validate_mutation_profile(m) for m in (mutation_profiles or [])]
    enforce_production_prohibition_for_release(mutations, release_export=True)

    checksums: dict[str, str] = {}

    env_path = out / "environment_profile.json"
    checksums[str(env_path.name)] = _write_json(env_path, environment_profile)

    vp_dir = out / "verifier_profiles"
    vp_dir.mkdir(exist_ok=True)
    for i, vp in enumerate(verifier_profiles):
        name = f"{vp.get('verifier_id', f'verifier_{i}')}.json".replace("/", "_")
        checksums[f"verifier_profiles/{name}"] = _write_json(vp_dir / name, vp)

    def _dump_list(subdir: str, items: list[Mapping[str, Any]], prefix: str) -> None:
        d = out / subdir
        d.mkdir(exist_ok=True)
        for i, item in enumerate(items):
            public_item = dict(item)
            if not include_revealed_adjudications:
                public_item.pop("adjudication", None)
                if public_item.get("revealed") is True:
                    public_item["revealed"] = False
                _assert_no_hidden_labels(public_item, path=f"{subdir}/{i}")
            name = f"{prefix}_{i:04d}.json"
            checksums[f"{subdir}/{name}"] = _write_json(d / name, public_item)

    _dump_list("trajectories", trajectories, "traj")
    _dump_list("snapshots", snapshots, "snap")
    _dump_list("reward_evidence", reward_evidence, "ree")
    _dump_list("verifier_results", verifier_results, "vres")
    _dump_list("adjudications_or_commitments", commitments, "commit")
    _dump_list("exploit_manifests", exploit_manifests, "exploit")
    _dump_list("counterfactual_branches", counterfactual_branches, "branch")
    if mutations:
        _dump_list("mutation_profiles", mutations, "mut")

    # Schema-validate reward evidence envelopes when present
    from labtrust_gym.errors import PolicyLoadError
    from labtrust_gym.policy.loader import load_json, validate_against_schema

    envelope_schema = (
        Path(__file__).resolve().parents[4]
        / "policy"
        / "schemas"
        / "pcs"
        / "RewardEvidenceEnvelope.v1.schema.json"
    )
    for ree in reward_evidence:
        try:
            validate_against_schema(dict(ree), load_json(envelope_schema), path=envelope_schema)
        except PolicyLoadError as exc:
            raise CampaignExportError(f"reward evidence schema invalid: {exc}") from exc

    assurance = {
        "artifact_kind": "VerifierAssuranceReport",
        "version": "1",
        "campaign_id": campaign_id,
        "status": "complete",
        "trajectory_count": len(trajectories),
        "exploit_count": len(exploit_manifests),
        "branch_count": len(counterfactual_branches),
        "claim_boundary": CLAIM_BOUNDARY,
        "non_claim": "Simulation/research only; no production clinical assurance.",
    }
    checksums["assurance_report.pcs.json"] = _write_json(out / "assurance_report.pcs.json", assurance)

    manifest = {
        "artifact_kind": "CampaignManifest",
        "version": "1",
        "campaign_id": campaign_id,
        "required_tree": list(REQUIRED_TREE),
        "checksums": checksums,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    checksums["campaign_manifest.pcs.json"] = _write_json(out / "campaign_manifest.pcs.json", manifest)
    # Update manifest with its own checksum after write — freeze by rewriting release_manifest
    release = {
        "artifact_kind": "VAReleaseManifest",
        "version": "1",
        "campaign_id": campaign_id,
        "checksums": checksums,
        "reconstruction": {
            "command": "python -m labtrust_gym.verifier_assurance.campaign.reconstruct --pack <dir>",
            "notes": "Clean-checkout reconstruction validates checksums and required tree.",
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }
    _write_json(out / "release_manifest.json", release)
    return {"campaign_id": campaign_id, "out_dir": str(out), "checksums": checksums}


def validate_campaign_pack(pack_dir: Path | str, *, allow_revealed: bool = False) -> dict[str, Any]:
    pack = Path(pack_dir)
    if not pack.is_dir():
        raise CampaignExportError(f"pack not found: {pack}")
    for name in REQUIRED_TREE:
        path = pack / name
        if not path.exists():
            raise CampaignExportError(f"missing required path: {name}")
    release = json.loads((pack / "release_manifest.json").read_text(encoding="utf-8"))
    checksums = release.get("checksums") or {}
    for rel, expected in checksums.items():
        path = pack / rel
        if not path.is_file():
            raise CampaignExportError(f"missing checksum target: {rel}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        # campaign_manifest may be written before final checksum map; verify non-manifest files strictly
        if rel == "campaign_manifest.pcs.json":
            continue
        if actual != expected:
            raise CampaignExportError(f"checksum mismatch: {rel}")
    # Hidden label exclusion
    for path in (pack / "adjudications_or_commitments").glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not allow_revealed:
            if doc.get("adjudication") is not None or doc.get("revealed") is True:
                raise CampaignExportError(f"hidden adjudication present in public pack: {path.name}")
        _assert_no_hidden_labels(
            {k: v for k, v in doc.items() if k != "adjudication" or allow_revealed},
            path=str(path),
        )
    # Validate reward evidence schemas on reconstruct
    from labtrust_gym.errors import PolicyLoadError
    from labtrust_gym.policy.loader import load_json, validate_against_schema

    envelope_schema = (
        Path(__file__).resolve().parents[4]
        / "policy"
        / "schemas"
        / "pcs"
        / "RewardEvidenceEnvelope.v1.schema.json"
    )
    for path in (pack / "reward_evidence").glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        try:
            validate_against_schema(doc, load_json(envelope_schema), path=envelope_schema)
        except PolicyLoadError as exc:
            raise CampaignExportError(f"reward evidence schema invalid: {path.name}: {exc}") from exc
    return {"valid": True, "campaign_id": release.get("campaign_id"), "claim_boundary": CLAIM_BOUNDARY}


def reconstruct_campaign(pack_dir: Path | str) -> dict[str, Any]:
    """Clean-checkout reconstruction entry: validate pack and return summary."""
    result = validate_campaign_pack(pack_dir)
    pack = Path(pack_dir)
    result["environment_profile"] = json.loads((pack / "environment_profile.json").read_text(encoding="utf-8"))
    result["assurance_report"] = json.loads((pack / "assurance_report.pcs.json").read_text(encoding="utf-8"))
    return result
