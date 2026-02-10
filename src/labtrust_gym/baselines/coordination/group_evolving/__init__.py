"""
Group-Evolving Agents (Experience Sharing) coordination method family.

Variant A: ExperienceSharingDeterministic - CI-safe, buffer within episode,
deterministic summaries at fixed intervals, adjust routing weights.

Variant B: GroupEvolvingStudy - population evolves across episodes,
fitness/select/mutate/recombine, checkpoint per generation (study track only).
"""

from labtrust_gym.baselines.coordination.group_evolving.method import (
    ExperienceSharingDeterministic,
    GroupEvolvingStudy,
)

__all__ = [
    "ExperienceSharingDeterministic",
    "GroupEvolvingStudy",
]
