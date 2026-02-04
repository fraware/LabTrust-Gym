"""Coordination method baselines for multi-agent lab at scale."""

from labtrust_gym.baselines.coordination.interface import (
    CoordinationMethod,
    action_dict_to_index_and_info,
)
from labtrust_gym.baselines.coordination.registry import make_coordination_method

__all__ = [
    "CoordinationMethod",
    "action_dict_to_index_and_info",
    "make_coordination_method",
]
