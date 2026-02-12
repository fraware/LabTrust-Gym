"""Golden runner, adapter interface, and emits validation."""

from labtrust_gym.runner.adapter import LabTrustEnvAdapter
from labtrust_gym.runner.adapters.pz_parallel_adapter import PZParallelAdapter
from labtrust_gym.runner.emits_validator import load_emits_vocab, validate_emits
from labtrust_gym.runner.golden_runner import (
    Failure,
    GoldenRunner,
    ScenarioReport,
    StepReport,
)


def get_default_env_adapter() -> LabTrustEnvAdapter:
    """
    Return the default env adapter for deterministic mode (no adapter provided).
    Uses PZParallelAdapter, which wraps the same engine as pz_parallel (CoreEnv).
    """
    return PZParallelAdapter()


__all__ = [
    "LabTrustEnvAdapter",
    "GoldenRunner",
    "Failure",
    "ScenarioReport",
    "StepReport",
    "PZParallelAdapter",
    "get_default_env_adapter",
    "load_emits_vocab",
    "validate_emits",
]
