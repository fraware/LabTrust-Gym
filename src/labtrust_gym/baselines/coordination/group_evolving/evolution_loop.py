"""
Evolution loop: fitness (throughput - violations - penalties), select top K,
mutate/recombine, checkpoint per generation. Study track only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.coordination.group_evolving.experience_buffer import (
    ExperienceBuffer,
)

GENOME_KEYS = ("routing_weights", "bid_shade")


def default_genome(zone_ids: list[str]) -> dict[str, Any]:
    """Single genome: routing_weights (zone -> float), bid_shade (float)."""
    return {
        "routing_weights": {z: 1.0 for z in zone_ids} if zone_ids else {},
        "bid_shade": 0.0,
    }


def fitness_from_metrics(
    episode_metrics: dict[str, Any],
    violation_penalty: float = 0.5,
    block_penalty: float = 0.3,
) -> float:
    """Fitness = throughput - violation_penalty * violations - block_penalty * blocks."""
    throughput = float(episode_metrics.get("throughput") or 0)
    violations = sum((episode_metrics.get("violations_by_invariant_id") or {}).values())
    blocks = sum((episode_metrics.get("blocked_by_reason_code") or {}).values())
    return throughput - violation_penalty * violations - block_penalty * blocks


def select_top_k(
    population: list[tuple[dict[str, Any], float]],
    k: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Select top k genomes by fitness; tie-break by seed-stable sort."""
    if not population or k <= 0:
        return []
    sorted_pop = sorted(
        population,
        key=(lambda x: (-x[1], json.dumps(x[0], sort_keys=True))),
    )
    return [g for g, _ in sorted_pop[:k]]


def mutate_genome(
    genome: dict[str, Any],
    seed: int,
    mutation_scale: float = 0.2,
) -> dict[str, Any]:
    """Copy genome and add small deterministic perturbation."""
    rng = __import__("random").Random(seed)
    out: dict[str, Any] = {}
    for key in GENOME_KEYS:
        val = genome.get(key)
        if isinstance(val, dict):
            out[key] = {k: max(0.01, v + (rng.random() - 0.5) * 2 * mutation_scale) for k, v in val.items()}
        elif isinstance(val, (int, float)):
            out[key] = max(0.0, val + (rng.random() - 0.5) * 2 * mutation_scale)
        else:
            out[key] = val
    return out


def recombine_genomes(
    g1: dict[str, Any],
    g2: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    """Uniform crossover per key."""
    rng = __import__("random").Random(seed)
    out: dict[str, Any] = {}
    for key in GENOME_KEYS:
        v1, v2 = g1.get(key), g2.get(key)
        if isinstance(v1, dict) and isinstance(v2, dict):
            keys = sorted(set(v1) | set(v2))
            out[key] = {k: v1.get(k, 1.0) if rng.random() < 0.5 else v2.get(k, 1.0) for k in keys}
        else:
            out[key] = v1 if rng.random() < 0.5 else v2
    return out


def save_checkpoint(
    run_dir: Path,
    gen_id: int,
    population: list[dict[str, Any]],
    buffer: ExperienceBuffer,
    mutation_log_entries: list[dict[str, Any]],
    seed: int,
) -> str:
    """
    Write coordination_learning/gen_XXX/checkpoint.json, buffer_digest.json,
    mutation_log.jsonl. Return checkpoint SHA (hash of checkpoint content).
    """
    base = run_dir / "coordination_learning" / f"gen_{gen_id:03d}"
    base.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "gen_id": gen_id,
        "population_size": len(population),
        "genomes": population,
        "buffer_digest_sha": buffer.digest_hash(seed),
    }
    checkpoint_path = base / "checkpoint.json"
    with checkpoint_path.open("w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, sort_keys=True)
    content = checkpoint_path.read_text(encoding="utf-8")
    checkpoint_sha = hashlib.sha256(content.encode()).hexdigest()[:16]

    buffer_digest = {
        "digest_sha": buffer.digest_hash(seed),
        "buffer_size": len(buffer),
        "seed": seed,
    }
    with (base / "buffer_digest.json").open("w", encoding="utf-8") as f:
        json.dump(buffer_digest, f, indent=2, sort_keys=True)

    mutation_log_path = base / "mutation_log.jsonl"
    with mutation_log_path.open("a", encoding="utf-8") as f:
        for entry in mutation_log_entries:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    return checkpoint_sha
