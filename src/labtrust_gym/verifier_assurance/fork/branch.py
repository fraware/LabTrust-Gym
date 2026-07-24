"""Fork / branch API with isolation and differential reports (LT-VA-05)."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any

from labtrust_gym.util.json_utils import canonical_json
from labtrust_gym.verifier_assurance.snapshot.canonical import (
    CanonicalSnapshot,
    capture_core_env,
    restore_core_env,
)

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"


class ForkError(ValueError):
    """Fail-closed fork/branch error."""


@dataclass
class BranchRecord:
    branch_id: str
    parent_snapshot_digest: str
    interventions: list[dict[str, Any]] = field(default_factory=list)
    policy_model_ids: list[str] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    terminal_state_digest: str | None = None
    public_verifier_decision: dict[str, Any] | None = None
    hidden_adjudication: dict[str, Any] | None = None
    reward_evidence_ids: list[str] = field(default_factory=list)
    resource_use: dict[str, Any] = field(default_factory=dict)
    claim_boundary: str = CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "BranchRecord.v1",
            "branch_id": self.branch_id,
            "parent_snapshot_digest": self.parent_snapshot_digest,
            "interventions": copy.deepcopy(self.interventions),
            "policy_model_ids": list(self.policy_model_ids),
            "trajectory": copy.deepcopy(self.trajectory),
            "terminal_state_digest": self.terminal_state_digest,
            "public_verifier_decision": copy.deepcopy(self.public_verifier_decision),
            "hidden_adjudication": copy.deepcopy(self.hidden_adjudication),
            "reward_evidence_ids": list(self.reward_evidence_ids),
            "resource_use": copy.deepcopy(self.resource_use),
            "claim_boundary": self.claim_boundary,
        }


@dataclass
class EnvBranch:
    """Isolated env branch rooted at a parent snapshot."""

    branch_id: str
    env: Any
    parent_digest: str
    record: BranchRecord

    def step(self, event: dict[str, Any]) -> dict[str, Any]:
        out = self.env.step(event)
        self.record.trajectory.append({"event": copy.deepcopy(event), "result": copy.deepcopy(out)})
        self.record.interventions.append({"type": "step", "event_id": event.get("event_id")})
        return out

    def seal_terminal(self) -> str:
        snap = capture_core_env(self.env)
        digest = snap.canonical_digest()
        self.record.terminal_state_digest = digest
        return digest


def fork_env(env: Any, *, branch_id: str, snapshot: CanonicalSnapshot | None = None) -> EnvBranch:
    """Create an isolated branch from snapshot (default: current env state)."""
    parent = snapshot if snapshot is not None else capture_core_env(env)
    parent_digest = parent.canonical_digest()
    # Deep isolation: new CoreEnv instance restored from parent
    from labtrust_gym.engine.core_env import CoreEnv

    child = CoreEnv()
    # Child must be reset with a compatible skeleton then overlay snapshot
    child.reset(
        {
            "timing_mode": getattr(env, "_timing_mode", "simulated") or "simulated",
            "specimens": [],
            "tokens": [],
        },
        deterministic=True,
        rng_seed=0,
    )
    restore_core_env(child, parent)
    record = BranchRecord(branch_id=branch_id, parent_snapshot_digest=parent_digest)
    return EnvBranch(branch_id=branch_id, env=child, parent_digest=parent_digest, record=record)


def differential_report(branch_a: EnvBranch, branch_b: EnvBranch) -> dict[str, Any]:
    """Compare two branches; bind parent digests."""
    if branch_a.parent_digest != branch_b.parent_digest:
        # Still allow report but flag divergence of parents
        parent_match = False
    else:
        parent_match = True
    ta = branch_a.record.terminal_state_digest
    tb = branch_b.record.terminal_state_digest
    if ta is None:
        branch_a.seal_terminal()
        ta = branch_a.record.terminal_state_digest
    if tb is None:
        branch_b.seal_terminal()
        tb = branch_b.record.terminal_state_digest
    report = {
        "schema_id": "BranchDifferentialReport.v1",
        "branch_a_id": branch_a.branch_id,
        "branch_b_id": branch_b.branch_id,
        "parent_digest_a": branch_a.parent_digest,
        "parent_digest_b": branch_b.parent_digest,
        "parent_digests_match": parent_match,
        "terminal_digest_a": ta,
        "terminal_digest_b": tb,
        "terminals_equal": ta == tb,
        "trajectory_len_a": len(branch_a.record.trajectory),
        "trajectory_len_b": len(branch_b.record.trajectory),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    report["report_digest"] = hashlib.sha256(canonical_json(report).encode("utf-8")).hexdigest()
    return report
