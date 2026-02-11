"""
Train PPO on TaskA (or other task) with fixed seeds and optional logging.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.marl.sb3_wrapper import make_task_env


def _make_reset_wrapper(gym_env: Any, task: Any) -> Any:
    """Wrap gym env so reset(seed) injects initial_state from task."""
    try:
        import gymnasium
    except ImportError:
        raise ImportError('Install with: pip install -e ".[marl]"') from None

    class ResetWrapper(gymnasium.Wrapper):  # type: ignore[type-arg]
        def __init__(self, env: Any, task: Any) -> None:
            super().__init__(env)
            self._task = task

        def reset(
            self,
            seed: int | None = None,
            options: dict[str, Any] | None = None,
        ) -> tuple[Any, dict[str, Any]]:
            options = dict(options or {})
            if seed is not None:
                options["initial_state"] = self._task.get_initial_state(seed)
            return self.env.reset(seed=seed, options=options or None)

    return ResetWrapper(gym_env, task)


def train_ppo(
    task_name: str = "throughput_sla",
    timesteps: int = 50_000,
    seed: int = 123,
    out_dir: Path | None = None,
    log_interval: int = 1000,
    verbose: int = 1,
) -> dict[str, Any]:
    """
    Train PPO on task with fixed seed. Saves model and eval metrics to out_dir.
    Returns dict with eval metrics and paths.
    """
    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.monitor import Monitor
    except ImportError:
        raise ImportError('stable-baselines3 is required for PPO. Install with: pip install -e ".[marl]"') from None

    from labtrust_gym.benchmarks.tasks import get_task

    task = get_task(task_name)
    gym_env, raw = make_task_env(
        task_name=task_name,
        max_steps=getattr(task, "max_steps", 80),
        reward_config=task.reward_config,
    )
    gym_env = _make_reset_wrapper(gym_env, task)
    gym_env = Monitor(gym_env)
    out_dir = Path(out_dir) if out_dir else Path("runs") / "ppo"
    out_dir.mkdir(parents=True, exist_ok=True)

    model = PPO(
        "MlpPolicy",
        gym_env,
        seed=seed,
        verbose=verbose,
        policy_kwargs=dict(net_arch=[64, 64]),
    )
    # Progress bar needs tqdm+rich (sb3[extra]); disable when unavailable
    try:
        import tqdm  # noqa: F401
        import rich  # noqa: F401
        use_progress_bar = verbose > 0
    except ImportError:
        use_progress_bar = False
    model.learn(
        total_timesteps=timesteps,
        log_interval=log_interval,
        progress_bar=use_progress_bar,
    )
    model_path = out_dir / "model.zip"
    model.save(str(model_path))
    gym_env.close()

    eval_metrics = _eval_policy(
        str(model_path),
        task_name=task_name,
        n_episodes=5,
        seed=seed + 1000,
    )
    metrics_path = out_dir / "eval_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(eval_metrics, f, indent=2)
    return {
        "model_path": str(model_path),
        "eval_metrics_path": str(metrics_path),
        "eval_metrics": eval_metrics,
        "task": task_name,
        "timesteps": timesteps,
        "seed": seed,
    }


def _eval_policy(
    model_path: str,
    task_name: str = "throughput_sla",
    n_episodes: int = 5,
    seed: int = 123,
) -> dict[str, Any]:
    """Run deterministic eval episodes and return metrics."""
    try:
        from stable_baselines3 import PPO
    except ImportError:
        return {}
    from labtrust_gym.benchmarks.tasks import get_task

    task = get_task(task_name)
    gym_env, _ = make_task_env(
        task_name=task_name,
        max_steps=getattr(task, "max_steps", 80),
        reward_config=task.reward_config,
    )
    gym_env = _make_reset_wrapper(gym_env, task)
    model = PPO.load(str(model_path))
    rewards: list[float] = []
    for ep in range(n_episodes):
        obs, _ = gym_env.reset(seed=seed + ep, options={})
        done = False
        ep_rew = 0.0
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, term, trunc, _ = gym_env.step(int(action))
            ep_rew += float(reward)
            done = term or trunc
        rewards.append(ep_rew)
    gym_env.close()
    return {
        "mean_reward": sum(rewards) / len(rewards) if rewards else 0.0,
        "episode_rewards": rewards,
        "n_episodes": n_episodes,
        "seed": seed,
    }
