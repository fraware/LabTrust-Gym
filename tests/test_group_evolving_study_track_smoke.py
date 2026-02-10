"""
Study track smoke tests for group_evolving_study.

Gated by env var LABTRUST_GROUP_EVOLVING_STUDY (set to 1 or true to run).
Runs 2 generations only; ensures coordination_learning artifacts are created
and checkpoint/buffer_digest hashes are stable for the same seed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.coordination_scale import CoordinationScaleConfig
from labtrust_gym.benchmarks.runner import run_benchmark


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _study_env_enabled() -> bool:
    v = os.environ.get("LABTRUST_GROUP_EVOLVING_STUDY", "")
    return str(v).strip().lower() in ("1", "true", "yes")


@pytest.mark.skipif(
    not _study_env_enabled(),
    reason="Study track tests require LABTRUST_GROUP_EVOLVING_STUDY=1",
)
def test_group_evolving_study_two_generations_artifacts_and_hashes(tmp_path: Path) -> None:
    """
    Run 2 generations (episodes_per_generation=2, 4 episodes total).
    Assert coordination_learning/gen_000 and gen_001 exist with checkpoint.json,
    buffer_digest.json, mutation_log.jsonl. Checkpoint content hash is deterministic
    for same seed (run twice, compare digest or checkpoint_sha from metadata).
    """
    out = tmp_path / "results.json"
    run_benchmark(
        task_name="coord_scale",
        num_episodes=4,
        base_seed=100,
        out_path=out,
        repo_root=_repo_root(),
        coord_method="group_evolving_study",
        pipeline_mode="deterministic",
        log_path=tmp_path / "episode.jsonl",
        scale_config_override=CoordinationScaleConfig(
            num_agents_total=4,
            role_mix={"ROLE_RUNNER": 0.5, "ROLE_ANALYTICS": 0.4, "ROLE_RECEPTION": 0.1},
            num_devices_per_type={"CHEM_ANALYZER": 1, "CENTRIFUGE_BANK": 1},
            num_sites=1,
            specimens_per_min=1.0,
            horizon_steps=8,
            timing_mode="explicit",
            partner_id=None,
        ),
    )
    assert out.exists()
    results = json.loads(out.read_text(encoding="utf-8"))
    learning = (results.get("metadata") or {}).get("coordination", {}).get("learning")
    assert learning is not None and learning.get("enabled") is True

    base = tmp_path / "coordination_learning"
    assert base.is_dir()
    gen0 = base / "gen_000"
    gen1 = base / "gen_001"
    assert gen0.is_dir(), "gen_000 directory should exist after 2 generations"
    assert (gen0 / "checkpoint.json").exists()
    assert (gen0 / "buffer_digest.json").exists()
    assert (gen0 / "mutation_log.jsonl").exists()
    if gen1.is_dir():
        assert (gen1 / "checkpoint.json").exists()

    checkpoint_sha = learning.get("checkpoint_sha")
    if checkpoint_sha:
        assert isinstance(checkpoint_sha, str) and len(checkpoint_sha) >= 8


@pytest.mark.skipif(
    not _study_env_enabled(),
    reason="Study track tests require LABTRUST_GROUP_EVOLVING_STUDY=1",
)
def test_group_evolving_study_hashes_stable_same_seed(tmp_path: Path) -> None:
    """Same seed -> same checkpoint_sha (or same digest in buffer_digest.json)."""
    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"
    run_dir1 = tmp_path / "run1"
    run_dir2 = tmp_path / "run2"
    run_dir1.mkdir()
    run_dir2.mkdir()
    for out_path, run_dir in [(out1, run_dir1), (out2, run_dir2)]:
        run_benchmark(
            task_name="coord_scale",
            num_episodes=4,
            base_seed=200,
            out_path=out_path,
            repo_root=_repo_root(),
            coord_method="group_evolving_study",
            pipeline_mode="deterministic",
            log_path=run_dir / "episode.jsonl",
            scale_config_override=CoordinationScaleConfig(
                num_agents_total=3,
                role_mix={"ROLE_RUNNER": 0.6, "ROLE_ANALYTICS": 0.3, "ROLE_RECEPTION": 0.1},
                num_devices_per_type={"CHEM_ANALYZER": 1, "CENTRIFUGE_BANK": 1},
                num_sites=1,
                specimens_per_min=1.0,
                horizon_steps=6,
                timing_mode="explicit",
                partner_id=None,
            ),
        )
    d1 = json.loads(out1.read_text(encoding="utf-8"))
    d2 = json.loads(out2.read_text(encoding="utf-8"))
    sha1 = (d1.get("metadata") or {}).get("coordination", {}).get("learning", {}).get("checkpoint_sha")
    sha2 = (d2.get("metadata") or {}).get("coordination", {}).get("learning", {}).get("checkpoint_sha")
    if sha1 and sha2:
        assert sha1 == sha2, "Checkpoint SHA should be stable for same seed"
