"""
Tests for live orchestrator: run dir structure, defense transition, and decision artifact.
Deterministic backend only (no network). Reviewer can verify via verify-bundle when
EvidenceBundle is produced from compatible episode log.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.orchestrator.config import OrchestratorConfig
from labtrust_gym.orchestrator.live import run_live_orchestrator


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_live_orchestrator_produces_standard_run_dir(tmp_path: Path) -> None:
    """Run live orchestrator (deterministic); assert run dir has cells, summary, decision, defense_transition."""
    repo = _repo_root()
    config = OrchestratorConfig(
        run_dir=tmp_path / "run",
        chosen_method_id="llm_central_planner",
        policy_root=repo,
        scale_id="small_smoke",
        injection_id=None,
        num_episodes=1,
        base_seed=42,
        llm_backend="deterministic",
        allow_network=False,
    )
    result = run_live_orchestrator(config)
    run_dir = Path(result["run_dir"])
    assert run_dir.is_dir()
    assert (run_dir / "cells").is_dir()
    cell_id = result["cell_id"]
    cell_dir = run_dir / "cells" / cell_id
    assert cell_dir.is_dir()
    assert (cell_dir / "results.json").is_file()
    assert (cell_dir / "defense_transition.json").is_file()
    assert (run_dir / "summary" / "summary_coord.csv").is_file()
    assert (run_dir / "metadata.json").is_file()
    defense = json.loads((cell_dir / "defense_transition.json").read_text(encoding="utf-8"))
    assert "attack_detected" in defense
    assert "defense_state" in defense
    if (run_dir / "COORDINATION_DECISION.v0.1.json").exists():
        decision = json.loads((run_dir / "COORDINATION_DECISION.v0.1.json").read_text(encoding="utf-8"))
        assert decision.get("verdict") in ("admissible", "no_admissible_method")
        assert "scale_decisions" in decision


def test_defense_controller_resume_requires_token() -> None:
    """DefenseController.resume_risky_operations requires matching token when FROZEN and token set."""
    from labtrust_gym.orchestrator.defense import DefenseController, DefenseState

    dc = DefenseController(human_override_token="secret")
    dc.state = DefenseState.FROZEN
    assert dc.resume_risky_operations("wrong") is False
    assert dc.state == DefenseState.FROZEN
    assert dc.resume_risky_operations("secret") is True
    assert dc.state == DefenseState.NORMAL
