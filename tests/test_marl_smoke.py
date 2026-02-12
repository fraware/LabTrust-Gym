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
        if (
            "1114" in err
            or "DLL" in err
            or "c10" in err.lower()
            or "access violation" in err.lower()
        ):
            pytest.skip(_MARL_SKIP_MSG + hint + (f" Raw: {err[:200]}" if err else ""))
        pytest.skip(
            f"stable_baselines3 not available: {err or result.returncode}{hint}"
        )


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
        pytest.skip(
            "MARL smoke subprocess timed out; run test_marl_smoke.py with LABTRUST_MARL_SMOKE=1"
        )
    if result.returncode != 0:
        out = (result.stdout or "") + (result.stderr or "")
        if (
            "1114" in out
            or "c10.dll" in out.lower()
            or "DLL" in out
            or "access violation" in out.lower()
        ):
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
