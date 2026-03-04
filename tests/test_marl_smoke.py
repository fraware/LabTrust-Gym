"""
MARL smoke test: PPO train/eval pipeline (guarded by LABTRUST_MARL_SMOKE=1).

On Windows, torch can crash the process (access violation / c10.dll) when the
default PyPI wheel conflicts with CUDA or VC++ runtime. We run the test body in
a subprocess so the main pytest process never imports torch.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_MARL_SKIP_MSG = (
    "stable_baselines3/torch failed to load (DLL/runtime). "
    "On Windows, use a torch build matching your CUDA/VC++ setup or "
    "install CPU-only: pip install torch --index-url https://download.pytorch.org/whl/cpu"
)


def _probe_sb3_subprocess() -> subprocess.CompletedProcess[str]:
    """Run 'import stable_baselines3' in a subprocess. Caller checks returncode."""
    return subprocess.run(
        [sys.executable, "-c", "import stable_baselines3"],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "LABTRUST_MARL_SMOKE": "1"},
    )


def _require_sb3_or_skip() -> None:
    """Skip if stable_baselines3 (torch) cannot be loaded in a subprocess."""
    try:
        result = _probe_sb3_subprocess()
    except subprocess.TimeoutExpired:
        pytest.skip("stable_baselines3 import timed out (torch may be loading)")
    except Exception as e:
        pytest.skip(f"Could not probe stable_baselines3: {e}")

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:500]
        hint = f" (Python: {sys.executable})"
        if "1114" in err or "DLL" in err or "c10" in err.lower() or "access violation" in err.lower():
            pytest.skip(_MARL_SKIP_MSG + hint + (f" Raw: {err[:200]}" if err else ""))
        pytest.skip(f"stable_baselines3 not available: {err or result.returncode}{hint}")


def _run_test_in_subprocess(test_name: str) -> None:
    """Run this module's test in a subprocess so the main process never imports torch."""
    env = {**os.environ, "LABTRUST_MARL_SMOKE": "1", "MARL_RUN_INLINE": "1"}
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(Path(__file__).resolve()),
                "-v",
                "--tb=short",
                "-k",
                test_name,
            ],
            env=env,
            timeout=300,
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("MARL smoke subprocess timed out; run test_marl_smoke.py with LABTRUST_MARL_SMOKE=1")
    if result.returncode != 0:
        out = (result.stdout or "") + (result.stderr or "")
        if "1114" in out or "c10.dll" in out.lower() or "DLL" in out or "access violation" in out.lower():
            pytest.skip(_MARL_SKIP_MSG)
        pytest.fail(f"MARL smoke test failed in subprocess (exit {result.returncode})")


def test_marl_smoke_ppo_train_tiny() -> None:
    """With LABTRUST_MARL_SMOKE=1, train PPO for tiny steps and ensure no crash."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_smoke_ppo_train_tiny")
        return
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        result = train_ppo(
            task_name="throughput_sla",
            timesteps=500,
            seed=42,
            out_dir=out,
            log_interval=250,
            verbose=0,
        )
        assert Path(result["model_path"]).exists()
        assert "eval_metrics" in result
        assert "mean_reward" in result["eval_metrics"]


def test_marl_smoke_ppo_train_config_and_history() -> None:
    """Train with train_config (obs_history_len, net_arch); check train_config.json (LABTRUST_MARL_SMOKE=1)."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_smoke_ppo_train_config_and_history")
        return
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    import json

    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        result = train_ppo(
            task_name="throughput_sla",
            timesteps=400,
            seed=43,
            out_dir=out,
            log_interval=200,
            verbose=0,
            train_config={"obs_history_len": 2, "net_arch": [32, 32]},
        )
        assert Path(result["model_path"]).exists()
        assert "eval_metrics" in result
        cfg_path = out / "train_config.json"
        assert cfg_path.exists(), "train_config.json must be written at start of training"
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        assert cfg.get("obs_history_len") == 2
        assert cfg.get("net_arch") == [32, 32]
        assert "mean_reward" in result["eval_metrics"]


def test_marl_smoke_ppo_eval() -> None:
    """With LABTRUST_MARL_SMOKE=1, run eval after a tiny train."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_smoke_ppo_eval")
        return
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.marl.ppo_eval import eval_ppo
    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        train_ppo(
            task_name="throughput_sla",
            timesteps=300,
            seed=7,
            out_dir=out,
            verbose=0,
        )
        model_path = out / "model.zip"
        metrics = eval_ppo(
            model_path=str(model_path),
            task_name="throughput_sla",
            episodes=2,
            seed=100,
            out_path=out / "eval_out.json",
        )
        assert "mean_reward" in metrics
        assert "episode_rewards" in metrics
        assert len(metrics["episode_rewards"]) == 2
        assert (out / "eval_out.json").exists()


def test_marl_ppo_propose_actions_scenario_no_crash() -> None:
    """With checkpoint (model_path from env or from a just-trained run), propose_actions runs without crash. Skip if no checkpoint."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_ppo_propose_actions_scenario_no_crash")
        return
    checkpoint = os.environ.get("LABTRUST_MARL_PPO_CHECKPOINT")
    if not checkpoint or not Path(checkpoint).exists():
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ppo"
            pytest.importorskip("gymnasium")
            from labtrust_gym.baselines.marl.ppo_train import train_ppo

            result = train_ppo(
                task_name="throughput_sla",
                timesteps=200,
                seed=99,
                out_dir=out,
                verbose=0,
            )
            checkpoint = result.get("model_path") if result else None
    if not checkpoint or not Path(checkpoint).exists():
        pytest.skip("No marl_ppo checkpoint (train completed or set LABTRUST_MARL_PPO_CHECKPOINT)")
    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    policy = {"zone_layout": {"zones": []}, "pz_to_engine": {"a0": "ops_0", "a1": "runner_0"}}
    scale_config = {"model_path": str(checkpoint), "seed": 42}
    coord = make_coordination_method(
        "marl_ppo",
        policy,
        repo_root=Path(__file__).resolve().parent.parent,
        scale_config=scale_config,
        model_path=str(checkpoint),
    )
    coord.reset(42, policy, scale_config)
    obs = {
        "a0": {"zone_id": "Z_A", "queue_by_device": [], "queue_has_head": [0], "log_frozen": 0},
        "a1": {"zone_id": "Z_B", "queue_by_device": [], "queue_has_head": [0], "log_frozen": 0},
    }
    actions = coord.propose_actions(obs, {}, 0)
    assert isinstance(actions, dict)
    assert set(actions.keys()) == {"a0", "a1"}
    for rec in actions.values():
        assert "action_index" in rec
        assert 0 <= rec["action_index"] <= 5


def _minimal_obs_for_agent() -> dict:
    """Minimal obs dict compatible with _flatten_obs (n_d=6, n_status=8)."""
    return {
        "my_zone_idx": 0,
        "door_restricted_open": 0,
        "door_restricted_duration_s": 0.0,
        "restricted_zone_frozen": 0,
        "queue_lengths": [0] * 6,
        "queue_has_head": [0] * 6,
        "specimen_status_counts": [0] * 8,
        "device_qc_pass": [1] * 6,
        "log_frozen": 0,
        "token_count_override": 0,
        "token_count_restricted": 0,
    }


def test_marl_ppo_propose_actions_all_five_agent_indices() -> None:
    """Train with include_agent_id=True, num_agents=5; propose_actions for all 5 agents; assert valid actions."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_ppo_propose_actions_all_five_agent_indices")
        return
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    from labtrust_gym.baselines.coordination.registry import make_coordination_method
    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        train_ppo(
            task_name="throughput_sla",
            timesteps=400,
            seed=44,
            out_dir=out,
            verbose=0,
            train_config={"include_agent_id": True, "num_agents": 5},
        )
        checkpoint = out / "model.zip"
        assert checkpoint.exists()
        policy = {"zone_layout": {"zones": []}}
        scale_config = {"model_path": str(checkpoint), "seed": 44}
        repo_root = Path(__file__).resolve().parent.parent
        coord = make_coordination_method(
            "marl_ppo",
            policy,
            repo_root=repo_root,
            scale_config=scale_config,
            model_path=str(checkpoint),
        )
        coord.reset(44, policy, scale_config)
        agents = ["ops_0", "runner_0", "runner_1", "qc_0", "supervisor_0"]
        obs = {aid: _minimal_obs_for_agent() for aid in agents}
        actions = coord.propose_actions(obs, {}, 0)
        assert isinstance(actions, dict)
        assert len(actions) == 5
        assert set(actions.keys()) == set(agents)
        for aid in agents:
            rec = actions[aid]
            assert "action_index" in rec
            assert 0 <= rec["action_index"] <= 5, f"agent {aid} action_index out of range"


def test_marl_ppo_full_episode_in_env() -> None:
    """One full episode with marl_ppo as coordinator in real env; assert episode completes and metrics present."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_ppo_full_episode_in_env")
        return
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    from labtrust_gym.baselines.coordination.registry import make_coordination_method
    from labtrust_gym.baselines.marl.ppo_train import train_ppo
    from labtrust_gym.benchmarks.runner import run_episode
    from labtrust_gym.benchmarks.tasks import get_task
    from labtrust_gym.domain import get_domain_adapter_factory
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    repo_root = Path(__file__).resolve().parent.parent
    policy_dir = repo_root / "policy"
    _adapter_fn = get_domain_adapter_factory("hospital_lab")
    if _adapter_fn is None:
        from labtrust_gym.domain.lab_adapter import lab_domain_adapter_factory

        _adapter_fn = lab_domain_adapter_factory

    def _engine_factory() -> Any:
        return _adapter_fn({}, None)

    def env_factory(
        initial_state: dict[str, Any],
        reward_config: dict[str, Any],
        log_path: Path | None = None,
    ) -> Any:
        return LabTrustParallelEnv(
            num_runners=2,
            num_adversaries=0,
            num_insiders=0,
            dt_s=10,
            reward_config=reward_config,
            policy_dir=policy_dir,
            log_path=log_path,
            engine_factory=_engine_factory,
        )

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        train_ppo(
            task_name="throughput_sla",
            timesteps=300,
            seed=45,
            out_dir=out,
            verbose=0,
        )
        checkpoint = out / "model.zip"
        assert checkpoint.exists()
        task = get_task("throughput_sla")
        coord = make_coordination_method(
            "marl_ppo",
            {},
            repo_root=repo_root,
            scale_config={"model_path": str(checkpoint)},
            model_path=str(checkpoint),
        )
        metrics, step_results_per_step = run_episode(
            task,
            episode_seed=46,
            env_factory=env_factory,
            coord_method=coord,
            repo_root=repo_root,
        )
    assert isinstance(metrics, dict)
    assert isinstance(step_results_per_step, list)
    assert "steps" in metrics or "episode_reward" in metrics or len(step_results_per_step) > 0


def test_marl_ppo_multi_agent_training_ops_and_runner() -> None:
    """Train with controlled_agents=[ops_0, runner_0]; load in marl_ppo; propose_actions for both; assert valid actions."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_ppo_multi_agent_training_ops_and_runner")
        return
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    from labtrust_gym.baselines.coordination.registry import make_coordination_method
    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        train_ppo(
            task_name="throughput_sla",
            timesteps=600,
            seed=47,
            out_dir=out,
            verbose=0,
            train_config={
                "include_agent_id": True,
                "num_agents": 5,
                "controlled_agents": ["ops_0", "runner_0"],
            },
        )
        checkpoint = out / "model.zip"
        assert checkpoint.exists()
        import json as _json

        with open(out / "train_config.json", encoding="utf-8") as f:
            cfg = _json.load(f)
        assert cfg.get("controlled_agents") == ["ops_0", "runner_0"]
        policy = {}
        scale_config = {"model_path": str(checkpoint), "seed": 47}
        repo_root = Path(__file__).resolve().parent.parent
        coord = make_coordination_method(
            "marl_ppo",
            policy,
            repo_root=repo_root,
            scale_config=scale_config,
            model_path=str(checkpoint),
        )
        coord.reset(47, policy, scale_config)
        obs = {
            "ops_0": _minimal_obs_for_agent(),
            "runner_0": _minimal_obs_for_agent(),
        }
        actions = coord.propose_actions(obs, {}, 0)
        assert set(actions.keys()) == {"ops_0", "runner_0"}
        for aid in ["ops_0", "runner_0"]:
            assert "action_index" in actions[aid]
            assert 0 <= actions[aid]["action_index"] <= 5


def test_marl_ctde_train_and_load() -> None:
    """Run CTDE training for a few hundred steps; load with eval and marl_ppo; assert no crash."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_ctde_train_and_load")
        return
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    from labtrust_gym.baselines.coordination.registry import make_coordination_method
    from labtrust_gym.baselines.marl.ctde_ppo_train import train_ctde_ppo

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ctde"
        result = train_ctde_ppo(
            task_name="throughput_sla",
            timesteps=400,
            seed=48,
            out_dir=out,
            verbose=0,
        )
        assert Path(result["model_path"]).exists()
        assert result.get("algorithm") == "ctde"
        import json as _json

        with open(out / "train_config.json", encoding="utf-8") as f:
            cfg = _json.load(f)
        assert cfg.get("algorithm") == "ctde"
        coord = make_coordination_method(
            "marl_ppo",
            {},
            repo_root=Path(__file__).resolve().parent.parent,
            scale_config={"model_path": result["model_path"]},
            model_path=result["model_path"],
        )
        coord.reset(48, {}, {})
        obs = {"ops_0": _minimal_obs_for_agent()}
        actions = coord.propose_actions(obs, {}, 0)
        assert "ops_0" in actions
        assert 0 <= actions["ops_0"]["action_index"] <= 5
        from stable_baselines3 import PPO

        model = PPO.load(str(result["model_path"]))
        obs_vec = _minimal_obs_for_agent()
        import numpy as np

        from labtrust_gym.baselines.marl.sb3_wrapper import _flatten_obs, _one_hot_agent

        flat = _flatten_obs(obs_vec, n_d=6, n_status=8)
        vec = np.concatenate([flat, _one_hot_agent(0, 5)]).astype(np.float32)
        action, _ = model.predict(vec, deterministic=True)
        assert 0 <= int(action) <= 5


def test_marl_ppo_learning_metadata_in_results() -> None:
    """Run benchmark with marl_ppo and model_path; assert results.metadata.coordination.learning has enabled and checkpoint_sha."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_ppo_learning_metadata_in_results")
        return
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    from labtrust_gym.baselines.marl.ppo_train import train_ppo
    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo_root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        train_ppo(
            task_name="throughput_sla",
            timesteps=300,
            seed=49,
            out_dir=out,
            verbose=0,
        )
        checkpoint = out / "model.zip"
        assert checkpoint.exists()
        scale_cfg = load_scale_config_by_id(repo_root, "small_smoke")
        results_path = Path(tmp) / "results.json"
        run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=50,
            out_path=results_path,
            repo_root=repo_root,
            coord_method="marl_ppo",
            scale_config_override=scale_cfg,
            initial_state_overrides={"model_path": str(checkpoint)},
        )
        import json as _json

        with open(results_path, encoding="utf-8") as f:
            results = _json.load(f)
        learning = (results.get("metadata") or {}).get("coordination", {}).get("learning")
        assert learning is not None, "results.metadata.coordination.learning should be set for marl_ppo"
        assert learning.get("enabled") is True
        assert "checkpoint_sha" in learning
        assert isinstance(learning["checkpoint_sha"], str)
        assert len(learning["checkpoint_sha"]) == 64


def test_marl_ppo_per_agent_agent_multiple_agent_ids() -> None:
    """MarlPPOPerAgentAgent returns valid actions for different agent_ids (scale path)."""
    if os.environ.get("LABTRUST_MARL_SMOKE") != "1":
        pytest.skip("Set LABTRUST_MARL_SMOKE=1 to run MARL smoke tests")
    _require_sb3_or_skip()
    if sys.platform == "win32" and os.environ.get("MARL_RUN_INLINE") != "1":
        _run_test_in_subprocess("test_marl_ppo_per_agent_agent_multiple_agent_ids")
        return
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    from labtrust_gym.baselines.marl.ppo_agent import MarlPPOPerAgentAgent
    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ppo"
        train_ppo(
            task_name="throughput_sla",
            timesteps=350,
            seed=51,
            out_dir=out,
            verbose=0,
            train_config={"include_agent_id": True, "num_agents": 5},
        )
        checkpoint = out / "model.zip"
        assert checkpoint.exists()
        agent_order = ["worker_0", "worker_1", "worker_2"]
        per_agent = MarlPPOPerAgentAgent(
            model_path=checkpoint,
            agent_order=agent_order,
            repo_root=Path(__file__).resolve().parent.parent,
        )
        obs = _minimal_obs_for_agent()
        for i, aid in enumerate(agent_order):
            action_idx, action_info = per_agent.act(obs, aid)
            assert isinstance(action_idx, int)
            assert 0 <= action_idx <= 5
            assert isinstance(action_info, dict)
