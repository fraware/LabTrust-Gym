"""
Live lab driver orchestration: deployable runtime for a chosen coordination method.

Runs the simulation with a selected coordination method, fallback baseline, and
optional defense controller (attack/invariant containment, kill_switch, human
override). Exposes OrchestratorConfig, DefenseController, and run_live_orchestrator.
"""

from labtrust_gym.orchestrator.config import OrchestratorConfig
from labtrust_gym.orchestrator.defense import DefenseController, DefenseState
from labtrust_gym.orchestrator.live import run_live_orchestrator

__all__ = [
    "OrchestratorConfig",
    "DefenseController",
    "DefenseState",
    "run_live_orchestrator",
]
