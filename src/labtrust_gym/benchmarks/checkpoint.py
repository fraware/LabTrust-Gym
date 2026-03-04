"""
Episode checkpoint and resume helpers for long or production-like runs.

Writes a checkpoint file (checkpoint.json) after each episode when run_dir and
checkpoint_every_n_episodes are set. Resume loads the checkpoint and returns
start_episode_index so the runner can skip completed episodes. Supports
"resume from episode K" for multi-episode runs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

CHECKPOINT_FILENAME = "checkpoint.json"


def write_checkpoint(
    run_dir: Path,
    episode_index: int,
    base_seed: int,
    num_episodes: int,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Write run_dir/checkpoint.json with episode progress so the run can be resumed.
    episode_index is the last completed episode (0-based); episodes_done = episode_index + 1.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "episode_index": episode_index,
        "episodes_done": episode_index + 1,
        "base_seed": base_seed,
        "num_episodes": num_episodes,
    }
    if extra:
        data["extra"] = extra
    path = run_dir / CHECKPOINT_FILENAME
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    _LOG.debug("Wrote checkpoint %s (episodes_done=%d)", path, data["episodes_done"])


def load_checkpoint(run_dir: Path) -> dict[str, Any] | None:
    """
    Load checkpoint from run_dir/checkpoint.json. Returns None if missing or invalid.
    Keys: episode_index, episodes_done, base_seed, num_episodes, optional extra.
    """
    path = Path(run_dir) / CHECKPOINT_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "episodes_done" not in data:
            return None
        return data
    except (OSError, json.JSONDecodeError) as e:
        _LOG.warning("Failed to load checkpoint %s: %s", path, e)
        return None


def start_episode_index_from_resume(run_dir: Path | None) -> int:
    """
    If run_dir contains a valid checkpoint, return episodes_done (first episode to run).
    Otherwise return 0.
    """
    if not run_dir:
        return 0
    ck = load_checkpoint(Path(run_dir))
    if ck is None:
        return 0
    return int(ck.get("episodes_done", 0))


# Step-level checkpoint (best-effort; same code version recommended).
STEP_CHECKPOINT_PREFIX = "checkpoint_step_"


def write_step_checkpoint(
    run_dir: Path,
    episode_index: int,
    step_index: int,
    base_seed: int,
    num_episodes: int,
    env_state: dict[str, Any] | None = None,
    rng_state: list[Any] | None = None,
) -> None:
    """
    Write a step-level checkpoint so the run can be resumed from this step.
    Uses a single file (overwritten each time) to save space when checkpoint_every_n_steps is set.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "episode_index": episode_index,
        "step_index": step_index,
        "base_seed": base_seed,
        "num_episodes": num_episodes,
    }
    if env_state is not None:
        data["env_state"] = env_state
    if rng_state is not None:
        data["rng_state"] = rng_state
    path = run_dir / f"{STEP_CHECKPOINT_PREFIX}latest.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    _LOG.debug(
        "Wrote step checkpoint %s (episode=%d step=%d)",
        path,
        episode_index,
        step_index,
    )


def load_step_checkpoint(run_dir: Path) -> dict[str, Any] | None:
    """
    Load step checkpoint from run_dir/checkpoint_step_latest.json.
    Returns None if missing or invalid. Keys: episode_index, step_index, base_seed,
    num_episodes, optional env_state, optional rng_state.
    """
    path = Path(run_dir) / f"{STEP_CHECKPOINT_PREFIX}latest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "episode_index" not in data:
            return None
        return data
    except (OSError, json.JSONDecodeError) as e:
        _LOG.warning("Failed to load step checkpoint %s: %s", path, e)
        return None
