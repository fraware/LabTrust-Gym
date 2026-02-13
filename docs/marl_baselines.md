# MARL baselines (PPO)

Minimal PPO baseline using stable-baselines3 on throughput_sla (or other tasks). Install the optional `[marl]` extra to use it.

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
labtrust train-ppo --task throughput_sla --timesteps 50000 --seed 123 --out runs/ppo
```

- `--task`: throughput_sla (default), stat_insertion, qc_cascade.
- `--timesteps`: Total training steps (default 50000).
- `--seed`: Random seed (default 123).
- `--out`: Directory for `model.zip` and `eval_metrics.json` (default `runs/ppo`).
- `--train-config PATH`: Path to a JSON file with `net_arch`, `obs_history_len`, `learning_rate`, `n_steps`, `reward_scale_schedule`. Example: `examples/ppo_train_config.example.json`. CLI flags `--net-arch`, `--obs-history-len`, `--learning-rate`, `--n-steps` override the file when set.
- `--obs-history-len N`: Stack last N observations (partial observability). Overrides file if set.
- `--learning-rate LR`: PPO learning rate. Overrides file if set.
- `--n-steps N`: PPO n_steps per update. Overrides file if set.

Example with config file:

```bash
labtrust train-ppo --task throughput_sla --timesteps 50000 --train-config examples/ppo_train_config.example.json --out runs/ppo
```

Example with CLI overrides only (no file):

```bash
labtrust train-ppo --task throughput_sla --obs-history-len 2 --learning-rate 1e-4 --out runs/ppo
```

Writes:

- `out_dir/model.zip`: Saved PPO model.
- `out_dir/train_config.json`: Training config (net_arch, obs_history_len, learning_rate, n_steps, device_ids). Written at training start so checkpoint evals and eval-ppo can use the same observation shape.
- `out_dir/eval_metrics.json`: Eval over 5 episodes after training (mean_reward, episode_rewards).

**train_config (optional):** Pass a dict via the API, or use `--train-config PATH` and/or `--obs-history-len`, `--learning-rate`, `--n-steps` on the CLI. Keys: `net_arch` (e.g. `[128, 128]`), `learning_rate`, `n_steps`, `obs_history_len`, `reward_scale_schedule` (list of `[step_frac, scale]` for reward curriculum). See `examples/ppo_train_config.example.json`.

### Eval

```bash
labtrust eval-ppo --model runs/ppo/model.zip --episodes 50 --seed 123 --out eval.json
```

- `--model`: Path to `model.zip`.
- `--task`: Task id (default throughput_sla).
- `--episodes`: Number of eval episodes (default 50).
- `--seed`: Base seed for episodes (default 123).
- `--out`: Optional path to write metrics JSON.

Eval loads `train_config.json` from the same directory as `model.zip` when present (e.g. `runs/ppo/train_config.json`). That ensures the eval environment uses the same `obs_history_len` (and thus observation shape) as training. If the file is missing, eval uses default obs_history_len=1.

## Smoke test (not in default CI)

Run MARL smoke only when the env var is set:

```bash
LABTRUST_MARL_SMOKE=1 pytest tests/test_marl_smoke.py -v
```

This trains PPO for a few hundred steps and runs eval to ensure the pipeline runs end-to-end. Omitted from default CI to avoid dependency and runtime cost.

## Reward design

The **throughput_sla** task uses two reward signals so PPO gets a learning signal even when no result is released in an episode:

- **throughput_reward** (1.0): Given to all agents when a step emits `RELEASE_RESULT` (e.g. when QC/supervisor release a result).
- **schedule_reward** (0.1): Given to the agent that performed an **accepted QUEUE_RUN** in that step. This provides dense reward for the scheduler (ops_0) so mean reward is non-zero during training.

Other tasks use only `throughput_reward` and optional penalties. Tune `reward_config` in `benchmarks/tasks.py` for your objective.

## Hyperparameter search (Optuna)

With the optional `[marl_hpo]` extra (`pip install -e ".[marl,marl_hpo]"`), you can run Optuna-based hyperparameter search:

- **API:** `from labtrust_gym.baselines.marl.ppo_train import run_ppo_optuna; run_ppo_optuna(task_name="throughput_sla", n_trials=16, timesteps_per_trial=20000, out_dir="runs/ppo_optuna")`
- Samples `learning_rate`, `net_arch` (small/medium/large), `n_steps`; runs `train_ppo` per trial; re-trains the best config at 2x timesteps and writes `optuna_study.json` and `best/` model.

Without the extra, calling `run_ppo_optuna` raises an ImportError pointing to the install command.

## Progress bar

Training uses a progress bar when **tqdm** and **rich** are installed (e.g. `pip install stable-baselines3[extra]`). If they are missing, training runs without a progress bar and no error is raised.

## Running benchmark with a trained PPO model

Use **eval-agent** with the built-in **PPOAgent** so the benchmark runner uses your saved model as ops_0:

```bash
# Set path to your model.zip (relative to repo root or absolute)
export LABTRUST_PPO_MODEL=labtrust_runs/ppo_10k/model.zip   # Linux/macOS
# PowerShell:
$env:LABTRUST_PPO_MODEL = "labtrust_runs/ppo_10k/model.zip"

labtrust eval-agent --task throughput_sla --episodes 5 --agent labtrust_gym.baselines.marl.ppo_agent:PPOAgent --out labtrust_runs/ppo_bench_results.json --seed 42
```

**PPOAgent** loads `train_config.json` from the model directory when present. It uses `device_ids` and `obs_history_len` from that file so QUEUE_RUN decoding and observation stacking match training. If the file is missing, it falls back to default device list and single-step observation.

Results are written in the same v0.2 format as other benchmarks so you can compare with scripted baselines via `summarize-results`.

## Multi-agent (shared policy with agent_id)

The **marl_ppo** coordination method uses a **shared PPO policy** with **agent_id in observation** (one-hot). Training with `labtrust train-ppo` (default `include_agent_id=True`, `num_agents=5`) produces a model that accepts `flat_obs + one_hot(agent_index)`; at coordination time each agent's obs is flattened, stacked with history if configured, and concatenated with one-hot so the same policy conditions on agent identity. The coordination security pack and full method lists exclude marl_ppo when no checkpoint is supplied. See [MARL multi-agent design](marl_multi_agent_design.md).

## Caveats

- **Windows / torch**: If MARL smoke tests skip with "DLL initialization routine failed" (WinError 1114), the default PyPI torch wheel can conflict with an existing CUDA/VC++ setup. Install a matching torch build (e.g. CPU-only: `pip install torch --index-url https://download.pytorch.org/whl/cpu`) or restore your previous torch/torchvision/torchaudio versions so they match.
- **Conda + venv**: If your prompt shows both a conda env and a venv (e.g. `(base) (labtrust-gym)` or `(gym) (labtrust-gym)`), `pip` may install into the conda env while `python`/`pytest` use the venv, so stable_baselines3 is missing where tests run. **Fix:** use a single environment. Option A: deactivate the venv (`deactivate`) so only conda is active; then `python -c "import stable_baselines3"` and, if needed, `pip install -e ".[marl]"` from the repo root. Option B: use only the venv (e.g. open a shell with no conda, activate venv, then `python -m pip install -e ".[dev,env,marl]"`). Then run `LABTRUST_MARL_SMOKE=1 pytest tests/test_marl_smoke.py -v`.
- **AMD / no CUDA**: CUDA is NVIDIA-only. On AMD (e.g. Ryzen with Radeon), use CPU-only PyTorch or DirectML. See [PyTorch on AMD or CPU-only](installation.md#pytorch-on-amd-or-cpu-only-no-cuda) in the installation guide.
- **Single-agent**: Only ops_0 is learned; runners are scripted. Multi-agent PPO would require a different setup (e.g. joint action space or independent learners).
- **Observation**: The wrapper flattens the ops_0 observation dict to a Box for SB3. With `obs_history_len > 1`, the last N flat observations are concatenated (partial observability). QUEUE_RUN uses device_ids from train_config or env default; PPOAgent reads device_ids from train_config.json when available.
- **Reward**: Uses the task’s reward_config (e.g. throughput_reward, schedule_reward, violation_penalty). Optional **reward_scale_schedule** in train_config (list of (step_frac, scale)) scales step reward for curriculum. See "Reward design" above.
- **Stability**: Small networks and short runs are for smoke and quick validation; for production-scale results, increase timesteps and tune hyperparameters.
