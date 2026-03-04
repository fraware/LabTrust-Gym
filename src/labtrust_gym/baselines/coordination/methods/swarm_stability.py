"""
Potential-field stability controls for swarm: inertia, congestion penalty, pheromone diffusion.
Used by swarm_stigmergy_priority and swarm_reactive. Reduces oscillation and herding.
"""

from __future__ import annotations


def inertia_term(
    current_direction: tuple[float, float],
    weight: float = 0.3,
) -> tuple[float, float]:
    """Inertia: damp direction change. weight in [0,1]."""
    return (current_direction[0] * weight, current_direction[1] * weight)


def congestion_penalty(
    zone_agent_count: int,
    scale: float = 0.5,
) -> float:
    """Penalty that increases with agent count in zone (reduces pile-ups)."""
    return scale * max(0, zone_agent_count - 1)


def pheromone_diffusion(
    neighbors: list[float],
    decay: float = 0.9,
) -> float:
    """Spread to neighbors with decay. neighbors = list of neighbor pheromone values."""
    if not neighbors:
        return 0.0
    return decay * (sum(neighbors) / len(neighbors))
