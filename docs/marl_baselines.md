# MARL baselines (PPO)

Minimal PPO baseline using stable-baselines3 on TaskA (or other tasks). Install the optional `[marl]` extra to use it.

## Installation

```bash
pip install -e ".[marl]"
```

This installs `stable-baselines3` and `gymnasium`. The PettingZoo env is wrapped to a single-agent Gymnasium env (ops_0 controlled by PPO; runners scripted).

## Reproducibility

- **Seeds**: Training and evaluation use fixed seeds (`--seed`). Same seed + same code => same training/eval behavior.
- **Determinism**: The underlying env is deterministic when `reset(seed=..., options={"initial_state": task.get_initial_state(seed)})` is used. PPO may use non-deterministic ops by default; evaluation uses `model.predict(obs, deterministic=True)`.

## CLI

### Train

```bash
labtrust train-ppo --task TaskA --timesteps 50000 --seed 123 --out runs/ppo
```

- `--task`: TaskA (default), TaskB, TaskC.
- `--timesteps`: Total training steps (default 50000).
- `--seed`: Random seed (default 123).
- `--out`: Directory for `model.zip` and `eval_metrics.json` (default `runs/ppo`).

Writes:

- `out_dir/model.zip`: Saved PPO model.
- `out_dir/eval_metrics.json`: Eval over 5 episodes after training (mean_reward, episode_rewards).

### Eval

```bash
labtrust eval-ppo --model runs/ppo/model.zip --episodes 50 --seed 123 --out eval.json
```

- `--model`: Path to `model.zip`.
- `--task`: Task name (default TaskA).
- `--episodes`: Number of eval episodes (default 50).
- `--seed`: Base seed for episodes (default 123).
- `--out`: Optional path to write metrics JSON.

## Smoke test (not in default CI)

Run MARL smoke only when the env var is set:

```bash
LABTRUST_MARL_SMOKE=1 pytest tests/test_marl_smoke.py -v
```

This trains PPO for a few hundred steps and runs eval to ensure the pipeline runs end-to-end. Omitted from default CI to avoid dependency and runtime cost.

## Caveats

- **Single-agent**: Only ops_0 is learned; runners are scripted. Multi-agent PPO would require a different setup (e.g. joint action space or independent learners).
- **Observation**: The wrapper flattens the ops_0 observation dict to a Box for SB3. QUEUE_RUN action uses placeholder work_id/device_id; for richer behavior, extend the action space or use heuristics to fill action_info.
- **Reward**: Uses the task’s reward_config (e.g. throughput_reward, violation_penalty). Tune for your objective.
- **Stability**: Small networks and short runs are for smoke/demo; for serious results, increase timesteps and tune hyperparameters.
