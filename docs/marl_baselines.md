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

Writes:

- `out_dir/model.zip`: Saved PPO model.
- `out_dir/eval_metrics.json`: Eval over 5 episodes after training (mean_reward, episode_rewards).

### Eval

```bash
labtrust eval-ppo --model runs/ppo/model.zip --episodes 50 --seed 123 --out eval.json
```

- `--model`: Path to `model.zip`.
- `--task`: Task id (default throughput_sla).
- `--episodes`: Number of eval episodes (default 50).
- `--seed`: Base seed for episodes (default 123).
- `--out`: Optional path to write metrics JSON.

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

Results are written in the same v0.2 format as other benchmarks so you can compare with scripted baselines via `summarize-results`.

## Caveats

- **Windows / torch**: If MARL smoke tests skip with "DLL initialization routine failed" (WinError 1114), the default PyPI torch wheel can conflict with an existing CUDA/VC++ setup. Install a matching torch build (e.g. CPU-only: `pip install torch --index-url https://download.pytorch.org/whl/cpu`) or restore your previous torch/torchvision/torchaudio versions so they match.
- **Conda + venv**: If your prompt shows both a conda env and a venv (e.g. `(base) (labtrust-gym)` or `(gym) (labtrust-gym)`), `pip` may install into the conda env while `python`/`pytest` use the venv, so stable_baselines3 is missing where tests run. **Fix:** use a single environment. Option A: deactivate the venv (`deactivate`) so only conda is active; then `python -c "import stable_baselines3"` and, if needed, `pip install -e ".[marl]"` from the repo root. Option B: use only the venv (e.g. open a shell with no conda, activate venv, then `python -m pip install -e ".[dev,env,marl]"`). Then run `LABTRUST_MARL_SMOKE=1 pytest tests/test_marl_smoke.py -v`.
- **AMD / no CUDA**: CUDA is NVIDIA-only. On AMD (e.g. Ryzen with Radeon), use CPU-only PyTorch or DirectML. See [PyTorch on AMD or CPU-only](installation.md#pytorch-on-amd-or-cpu-only-no-cuda) in the installation guide.
- **Single-agent**: Only ops_0 is learned; runners are scripted. Multi-agent PPO would require a different setup (e.g. joint action space or independent learners).
- **Observation**: The wrapper flattens the ops_0 observation dict to a Box for SB3. QUEUE_RUN action uses placeholder work_id/device_id; for richer behavior, extend the action space or use heuristics to fill action_info.
- **Reward**: Uses the task’s reward_config (e.g. throughput_reward, schedule_reward, violation_penalty). See "Reward design" above.
- **Stability**: Small networks and short runs are for smoke/demo; for serious results, increase timesteps and tune hyperparameters.
