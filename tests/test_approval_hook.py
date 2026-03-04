"""Tests for approval_callback (8.2): hook after propose_actions, before env.step."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from labtrust_gym.benchmarks.runner import run_benchmark


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_approval_callback_identity_pass_through() -> None:
    """With approval_callback returning None (pass-through), behavior unchanged."""
    repo = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results.json"
        results_no_cb = run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=repo,
            coord_method="centralized_planner",
            pipeline_mode="deterministic",
            allow_network=False,
            approval_callback=None,
        )
        throughput_no_cb = ((results_no_cb.get("episodes") or [{}])[0].get("metrics") or {}).get("throughput", 0)

        out_path2 = Path(tmp) / "results2.json"

        def _identity(actions_dict: dict[str, Any], action_infos: dict[str, dict[str, Any]]) -> None:
            return None  # pass through

        results_id = run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out_path2,
            repo_root=repo,
            coord_method="centralized_planner",
            pipeline_mode="deterministic",
            allow_network=False,
            approval_callback=_identity,
        )
        throughput_id = ((results_id.get("episodes") or [{}])[0].get("metrics") or {}).get("throughput", 0)
        assert throughput_id == throughput_no_cb, "Identity callback should not change throughput"


def test_approval_callback_all_noop_replaces_actions() -> None:
    """With callback that replaces all actions with NOOP, throughput is 0 (or no mutating actions)."""
    repo = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results_noop.json"
        from labtrust_gym.envs.action_contract import ACTION_INDEX_TO_TYPE

        noop_index = next(
            (i for i, t in ACTION_INDEX_TO_TYPE.items() if t == "NOOP"),
            0,
        )

        def _all_noop(
            actions_dict: dict[str, Any], action_infos: dict[str, dict[str, Any]]
        ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
            return (
                {aid: {"action_index": noop_index, "action_type": "NOOP", "args": {}} for aid in actions_dict},
                action_infos,
            )

        results = run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=repo,
            coord_method="centralized_planner",
            pipeline_mode="deterministic",
            allow_network=False,
            approval_callback=_all_noop,
        )
        throughput = ((results.get("episodes") or [{}])[0].get("metrics") or {}).get("throughput", 0)
        assert throughput == 0, "All-NOOP approval callback should yield zero throughput"
