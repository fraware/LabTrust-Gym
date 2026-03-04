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
    net_arch: list[int] | None = None,
    checkpoint_every_steps: int | None = None,
    keep_best_checkpoints: int = 0,
    train_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Train PPO on task with fixed seed. Saves model and eval metrics to out_dir.
    net_arch: policy MLP hidden sizes (default [64, 64]); e.g. [128, 128] or [64, 64, 64].
    train_config: optional dict with net_arch, learning_rate, n_steps, obs_history_len,
        reward_scale_schedule (list of (step_frac, scale) for curriculum).
    checkpoint_every_steps: if set, save checkpoint every N steps (e.g. 10000).
    keep_best_checkpoints: if > 0, run eval every checkpoint_every_steps and keep the best K by mean_reward.
    Returns dict with eval metrics and paths.
    """
    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.monitor import Monitor
    except ImportError:
        raise ImportError('stable-baselines3 is required for PPO. Install with: pip install -e ".[marl]"') from None

    from labtrust_gym.benchmarks.tasks import get_task

    cfg = dict(train_config or {})
    arch = (
        net_arch if net_arch is not None else cfg.get("net_arch") if isinstance(cfg.get("net_arch"), list) else [64, 64]
    )
    learning_rate = cfg.get("learning_rate") if isinstance(cfg.get("learning_rate"), (int, float)) else None
    n_steps = cfg.get("n_steps") if isinstance(cfg.get("n_steps"), int) else None

    task = get_task(task_name)
    reward_schedule: list[tuple[float, float]] = []
    raw_schedule = cfg.get("reward_scale_schedule")
    if isinstance(raw_schedule, list):
        for item in raw_schedule:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    reward_schedule.append((float(item[0]), float(item[1])))
                except (TypeError, ValueError):
                    pass
    include_agent_id = cfg.get("include_agent_id", True)
    if not isinstance(include_agent_id, bool):
        include_agent_id = bool(include_agent_id)
    num_agents = int(cfg.get("num_agents", 5))
    num_agents = max(1, min(num_agents, 64))
    controlled_agents = cfg.get("controlled_agents")
    if isinstance(controlled_agents, list) and controlled_agents:
        controlled_agents = [str(a) for a in controlled_agents]
    else:
        controlled_agents = ["ops_0"]
    gym_env, raw = make_task_env(
        task_name=task_name,
        max_steps=getattr(task, "max_steps", 80),
        reward_config=task.reward_config,
        obs_history_len=max(1, int(cfg.get("obs_history_len", 1))),
        reward_scale_schedule=reward_schedule if reward_schedule else None,
        include_agent_id=include_agent_id,
        num_agents=num_agents,
        controlled_agents=controlled_agents,
    )
    gym_env = _make_reset_wrapper(gym_env, task)
    gym_env = Monitor(gym_env)
    out_dir = Path(out_dir) if out_dir else Path("runs") / "ppo"
    out_dir.mkdir(parents=True, exist_ok=True)
    obs_history_len = max(1, int(cfg.get("obs_history_len", 1)))
    device_ids = getattr(raw, "_device_ids", None)
    if not device_ids:
        try:
            from labtrust_gym.envs.pz_parallel import DEFAULT_DEVICE_IDS

            device_ids = list(DEFAULT_DEVICE_IDS)
        except Exception:
            device_ids = []
    train_config_path = out_dir / "train_config.json"
    n_d = 6
    n_status = 8
    with open(train_config_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "net_arch": arch,
                "obs_history_len": obs_history_len,
                "learning_rate": float(learning_rate) if learning_rate is not None else 3e-4,
                "n_steps": int(n_steps) if n_steps is not None else 2048,
                "device_ids": device_ids,
                "n_d": n_d,
                "n_status": n_status,
                "include_agent_id": include_agent_id,
                "num_agents": num_agents,
                "controlled_agents": controlled_agents,
            },
            f,
            indent=2,
        )

    policy_kwargs: dict[str, Any] = {"net_arch": arch}
    model = PPO(
        "MlpPolicy",
        gym_env,
        seed=seed,
        verbose=verbose,
        policy_kwargs=policy_kwargs,
        learning_rate=float(learning_rate) if learning_rate is not None else 3e-4,
        n_steps=int(n_steps) if n_steps is not None else 2048,
    )
    try:
        import rich  # noqa: F401
        import tqdm  # noqa: F401

        use_progress_bar = verbose > 0
    except ImportError:
        use_progress_bar = False

    best_mean_reward: float | None = None
    checkpoint_every = checkpoint_every_steps if checkpoint_every_steps and checkpoint_every_steps > 0 else None

    if checkpoint_every is None or keep_best_checkpoints <= 0:
        model.learn(
            total_timesteps=timesteps,
            log_interval=log_interval,
            progress_bar=use_progress_bar,
        )
    else:
        step = 0
        first = True
        while step < timesteps:
            chunk = min(checkpoint_every, timesteps - step)
            model.learn(
                total_timesteps=chunk,
                log_interval=log_interval,
                progress_bar=use_progress_bar,
                reset_num_timesteps=first,
            )
            first = False
            step += chunk
            ckpt_path = out_dir / f"checkpoint_{step}.zip"
            model.save(str(ckpt_path))
            eval_metrics = _eval_policy(
                str(ckpt_path),
                task_name=task_name,
                n_episodes=3,
                seed=seed + 1000 + step,
                train_config_path=str(out_dir / "train_config.json")
                if (out_dir / "train_config.json").exists()
                else None,
            )
            mean_r = eval_metrics.get("mean_reward")
            if mean_r is not None and (best_mean_reward is None or mean_r > best_mean_reward):
                best_mean_reward = mean_r
                model.save(str(out_dir / "best_model.zip"))
        if (out_dir / "best_model.zip").exists():
            model = PPO.load(str(out_dir / "best_model.zip"))

    model_path = out_dir / "model.zip"
    model.save(str(model_path))
    gym_env.close()

    eval_metrics = _eval_policy(
        str(model_path),
        task_name=task_name,
        n_episodes=5,
        seed=seed + 1000,
        train_config_path=str(train_config_path),
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
        "net_arch": arch,
    }


def _eval_policy(
    model_path: str,
    task_name: str = "throughput_sla",
    n_episodes: int = 5,
    seed: int = 123,
    train_config_path: str | None = None,
) -> dict[str, Any]:
    """Run deterministic eval episodes and return metrics."""
    try:
        from stable_baselines3 import PPO
    except ImportError:
        return {}
    from labtrust_gym.benchmarks.tasks import get_task

    obs_history_len = 1
    include_agent_id = True
    num_agents = 5
    if train_config_path and Path(train_config_path).exists():
        try:
            with open(train_config_path, encoding="utf-8") as f:
                tc = json.load(f)
            obs_history_len = max(1, int(tc.get("obs_history_len", 1)))
            include_agent_id = bool(tc.get("include_agent_id", True))
            num_agents = max(1, int(tc.get("num_agents", 5)))
        except Exception:
            pass

    task = get_task(task_name)
    gym_env, _ = make_task_env(
        task_name=task_name,
        max_steps=getattr(task, "max_steps", 80),
        reward_config=task.reward_config,
        obs_history_len=obs_history_len,
        include_agent_id=include_agent_id,
        num_agents=num_agents,
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


def run_ppo_optuna(
    task_name: str = "throughput_sla",
    n_trials: int = 16,
    timesteps_per_trial: int = 20_000,
    seed: int = 123,
    out_dir: Path | None = None,
    timeout_s: float | None = None,
    n_eval_episodes: int = 5,
) -> dict[str, Any]:
    """
    Hyperparameter search for PPO via Optuna. Samples learning_rate, net_arch, n_steps.
    Requires optuna: pip install -e ".[marl_hpo]" or pip install optuna.
    Saves best model and study to out_dir; returns best params and eval metrics.
    """
    try:
        import optuna
    except ImportError:
        raise ImportError(
            'run_ppo_optuna requires optuna. Install with: pip install -e ".[marl_hpo]" or pip install optuna'
        ) from None

    out_dir = Path(out_dir) if out_dir else Path("runs") / "ppo_optuna"
    out_dir.mkdir(parents=True, exist_ok=True)

    def objective(trial: Any) -> float:  # trial: optuna.Trial
        learning_rate = trial.suggest_float("learning_rate", 1e-5, 1e-2, log=True)
        arch_choice = trial.suggest_categorical("net_arch", ["small", "medium", "large"])
        net_arch = {"small": [64, 64], "medium": [128, 128], "large": [256, 128]}[arch_choice]
        n_steps = trial.suggest_categorical("n_steps", [512, 1024, 2048, 4096])
        train_config = {
            "learning_rate": learning_rate,
            "net_arch": net_arch,
            "n_steps": n_steps,
        }
        trial_dir = out_dir / f"trial_{trial.number}"
        result = train_ppo(
            task_name=task_name,
            timesteps=timesteps_per_trial,
            seed=seed + trial.number,
            out_dir=trial_dir,
            verbose=0,
            train_config=train_config,
        )
        mean_reward = (result.get("eval_metrics") or {}).get("mean_reward")
        if mean_reward is None:
            return 0.0
        return float(mean_reward)

    study = optuna.create_study(direction="maximize")
    study.optimize(
        objective,
        n_trials=n_trials,
        timeout=timeout_s,
        show_progress_bar=True,
        n_jobs=1,
    )
    best_trial = study.best_trial
    if best_trial is None:
        return {"best_params": {}, "best_value": None, "study": None}

    best_config = {
        "learning_rate": best_trial.params.get("learning_rate"),
        "net_arch": best_trial.params.get("net_arch"),
        "n_steps": best_trial.params.get("n_steps"),
    }
    arch_map = {"small": [64, 64], "medium": [128, 128], "large": [256, 128]}
    net_arch_list = arch_map.get(best_trial.params.get("net_arch"), [64, 64])
    train_config = {
        "net_arch": net_arch_list,
        "learning_rate": best_config["learning_rate"],
        "n_steps": best_config["n_steps"],
    }
    best_dir = out_dir / "best"
    best_dir.mkdir(parents=True, exist_ok=True)
    final_result = train_ppo(
        task_name=task_name,
        timesteps=timesteps_per_trial * 2,
        seed=seed,
        out_dir=best_dir,
        verbose=1,
        train_config=train_config,
    )
    with open(out_dir / "optuna_study.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "best_params": best_trial.params,
                "best_value": best_trial.value,
                "n_trials": len(study.trials),
            },
            f,
            indent=2,
        )
    return {
        "best_params": best_trial.params,
        "best_value": best_trial.value,
        "best_result": final_result,
        "n_trials": len(study.trials),
    }
