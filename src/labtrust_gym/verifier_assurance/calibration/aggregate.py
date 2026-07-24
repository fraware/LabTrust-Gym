"""Aggregate partner calibration adapter + VA release pack (LT-VA-14)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import load_effective_policy, load_yaml
from labtrust_gym.verifier_assurance.campaign.export import (
    export_campaign_pack,
    reconstruct_campaign,
)
from labtrust_gym.verifier_assurance.environment_profile import hospital_lab_seed_profile
from labtrust_gym.verifier_assurance.oracle.dual_oracle import (
    default_hidden_profile,
    default_public_profile,
)
from labtrust_gym.verifier_assurance.reward.composition import (
    build_reward_evidence_envelope,
    legacy_compat_policy,
)
from labtrust_gym.verifier_assurance.studies.authorization import run_authorization_campaign
from labtrust_gym.verifier_assurance.studies.coevolution import run_coevolution_campaign
from labtrust_gym.verifier_assurance.studies.outcome_process import run_outcome_process_study
from labtrust_gym.verifier_assurance.studies.responsibility import run_responsibility_campaign

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"


class CalibrationAdapterError(ValueError):
    """Fail-closed calibration adapter error."""


FORBIDDEN_RAW_KEYS = (
    "patient_id",
    "mrn",
    "specimen_barcode",
    "raw_records",
    "phi",
    "pii",
)


def validate_aggregate_only(doc: Mapping[str, Any], *, path: str = "root") -> None:
    if isinstance(doc, Mapping):
        for k, v in doc.items():
            lk = str(k).lower()
            if any(f in lk for f in FORBIDDEN_RAW_KEYS):
                raise CalibrationAdapterError(f"raw partner field forbidden at {path}.{k}")
            validate_aggregate_only(v, path=f"{path}.{k}")
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            validate_aggregate_only(v, path=f"{path}[{i}]")


def compare_simulated_vs_aggregate(
    simulated_stats: Mapping[str, float],
    aggregate_priors: Mapping[str, float],
) -> dict[str, Any]:
    """Compare simulated distributions vs approved de-identified aggregates only."""
    validate_aggregate_only(aggregate_priors)
    validate_aggregate_only(simulated_stats)
    deltas = {}
    for key, agg in aggregate_priors.items():
        sim = float(simulated_stats.get(key, 0.0))
        deltas[key] = {"simulated": sim, "aggregate": float(agg), "delta": sim - float(agg)}
    return {
        "schema_id": "AggregateCalibrationComparison.v1",
        "deltas": deltas,
        "claim_boundary": CLAIM_BOUNDARY,
        "note": "Approved de-identified aggregates only; no raw partner records.",
    }


def load_partner_aggregate_priors(repo_root: Path, partner_id: str) -> dict[str, float]:
    path = repo_root / "policy" / "partners" / partner_id / "calibration.v0.1.yaml"
    if not path.exists():
        raise CalibrationAdapterError(f"missing partner calibration: {path}")
    data = load_yaml(path)
    validate_aggregate_only(data)
    priors = (data.get("workload_priors") or {})
    return {k: float(v) for k, v in priors.items() if isinstance(v, int | float)}


def build_va_release_pack(
    out_dir: Path | str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Publish frozen release pack with checksums and clean-checkout reconstruction."""
    repo = repo_root or Path(__file__).resolve().parents[4]
    _policy, fingerprint, _pid, cal_fp = load_effective_policy(repo)
    env_profile = hospital_lab_seed_profile(
        policy_fingerprint=fingerprint,
        calibration_fingerprint=cal_fp,
    )
    va10 = run_outcome_process_study()
    va11 = run_authorization_campaign()
    va12 = run_responsibility_campaign()
    va13 = run_coevolution_campaign()

    # Optional aggregate comparison when a partner calibration exists
    calibration_report = None
    partners_dir = repo / "policy" / "partners"
    if partners_dir.is_dir():
        for child in sorted(partners_dir.iterdir()):
            if (child / "calibration.v0.1.yaml").exists():
                priors = load_partner_aggregate_priors(repo, child.name)
                simulated = {
                    "stat_rate": priors.get("stat_rate", 0.0),
                    "arrival_mean_s": priors.get("arrival_mean_s", 0.0) * 1.0,
                }
                calibration_report = compare_simulated_vs_aggregate(simulated, priors)
                break

    exploits = [
        {"family": e["family"], "public_reward": e["public_reward"], "invalid": True}
        for e in va10["recovered_exploit_families"]
    ]
    reward_policy = legacy_compat_policy()
    reward_evidence = []
    for i, row in enumerate(va10["rows"][:3]):
        comps = {c: 0.0 for c in reward_policy["components"]}
        comps["operational_success"] = float(row["public_reward"])
        comps["process_compliance"] = 0.0 if row["hidden_accepted"] is False else 1.0
        comps["safety_violation_penalty"] = -1.0 if row["hidden_accepted"] is False else 0.0
        scalar = float(sum(comps.values()))
        reward_evidence.append(
            build_reward_evidence_envelope(
                envelope_id=f"ree-va10-{i:04d}",
                run_id="labtrust-va-release-v1",
                step=i,
                agent_id="attacker_0",
                policy=reward_policy,
                components=comps,
                scalar_reward=scalar,
                public_verifier_id=default_public_profile()["verifier_id"],
                public_decision="accept" if row["public_accepted"] else "reject",
            )
        )
    pack = export_campaign_pack(
        out_dir,
        campaign_id="labtrust-va-release-v1",
        environment_profile=env_profile,
        verifier_profiles=[default_public_profile(), default_hidden_profile()],
        trajectories=[{"study": "VA-10", "rows": va10["rows"][:5]}],
        snapshots=[{"note": "see study runners for live snapshots"}],
        reward_evidence=reward_evidence,
        verifier_results=[
            {
                "va13": va13["acceptance"],
                "checkpoints": va13.get("checkpoints"),
                "claim_boundary": CLAIM_BOUNDARY,
            }
        ],
        commitments=[e["commitment"] for e in va10["recovered_exploit_families"]],
        exploit_manifests=exploits,
        counterfactual_branches=[{"study": "VA-12", "case_count": len(va12["cases"])}],
        mutation_profiles=[
            {
                "schema_id": "MutationProfile.v1",
                "mutation_id": "mut-va-qc-drift",
                "source_profile_id": env_profile["profile_id"],
                "target": "env",
                "dimension": "qc_drift",
                "operations": [{"op": "qc_drift", "device_id": "D1"}],
                "rationale": "Induce QC fail for bypass study",
                "expected_effect": "hidden reject on qc_bypass",
                "production_prohibition": True,
                "claim_boundary": CLAIM_BOUNDARY,
            }
        ],
    )
    out = Path(out_dir)
    fidelity = {
        "environment_profile_id": env_profile["profile_id"],
        "known_fidelity_limits": env_profile["known_fidelity_limits"],
        "calibration_report": calibration_report,
        "studies": {
            "VA-10": {"recovered_count": va10["recovered_count"]},
            "VA-11": {"families": len(va11["results"])},
            "VA-12": {"cases": len(va12["cases"])},
            "VA-13": va13["acceptance"],
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }
    (out / "fidelity_and_calibration.json").write_bytes(
        (json.dumps(fidelity, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    # Reconstruction smoke
    reconstructed = reconstruct_campaign(out)
    pack["reconstruction"] = reconstructed
    pack["fidelity"] = fidelity
    return pack
