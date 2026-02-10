# Installation

## Pip (PyPI)

Install the package with optional extras for the environment and plots:

```bash
pip install labtrust-gym[env,plots]
```

- **env**: PettingZoo and Gymnasium (required for benchmarks and quick-eval).
- **plots**: Matplotlib (for study figures and data tables).

Check version and optional git SHA:

```bash
labtrust --version
```

When installed from a wheel, policy files are bundled in the package. When developing from source, policy is read from the repo `policy/` directory. You can override the policy location with the `LABTRUST_POLICY_DIR` environment variable (path to the policy directory).

## Configuration (no .env file required)

LabTrust-Gym **does not load a `.env` file**. All configuration is via **environment variables** (set in your shell or CI). You do **not** need to create a `.env` file for normal use.

Optional env vars (all have defaults or CLI overrides):

| Variable | Purpose |
|----------|---------|
| `LABTRUST_POLICY_DIR` | Path to policy directory (overrides package/repo policy). |
| `LABTRUST_PARTNER` | Partner overlay ID (e.g. `hsl_like`); same as `--partner` on CLI. |
| `LABTRUST_STRICT_SIGNATURES` | Set to `1` to enable strict signature verification in the engine. |
| `LABTRUST_STRICT_REASON_CODES` | Set to `1` so golden runner requires reason codes in registry. |
| `LABTRUST_REPRO_SMOKE` | Set to `1` / `true` / `yes` for reproduce/study smoke (1 episode per condition). |
| `LABTRUST_PAPER_SMOKE` | Set to `1` / `true` / `yes` for package-release paper_v0.1 smoke (few episodes). |
| `LABTRUST_RUN_GOLDEN` | Set to `1` to run full golden suite in tests (e.g. `pytest test_golden_suite.py`). |
| `LABTRUST_LOCAL_LLM_URL` | Base URL for local LLM (e.g. Ollama). Used when `--llm-backend ollama_live`. Default: `http://localhost:11434`. |
| `LABTRUST_LOCAL_LLM_MODEL` | Model name for local LLM (e.g. `llama3.2`). Used when `--llm-backend ollama_live`. |
| `LABTRUST_LOCAL_LLM_TIMEOUT` | Request timeout in seconds for local LLM. Default: 60. |

### Loading a .env file (optional)

The code **does not load `.env` automatically**. If you use a `.env` file for API keys or other overrides, you must load it yourself **before** running any command; otherwise you may see "provider X doesn't work" when the cause is missing env injection.

**macOS / Linux (bash/zsh):**

```bash
set -a
source .env
set +a
```

**Windows (PowerShell):**

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*#') { return }
  if ($_ -match '^\s*$') { return }
  $k,$v = $_ -split '=',2
  [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim().Trim('"'), "Process")
}
```

**Sanity check (any OS):**

```bash
python -c "import os; print('OPENAI', bool(os.getenv('OPENAI_API_KEY'))); print('ANTHROPIC', bool(os.getenv('ANTHROPIC_API_KEY')))"
```

### LLMs: no API keys required by default

The **LLM baselines** (benchmarks, tests, quick-eval) do **not** call any external API by default. They use **deterministic, offline backends**:

- **DeterministicConstrainedBackend** — Official LLM baseline: chooses from allowed actions with a **seeded RNG**; no network, no API key.
- **MockDeterministicBackend** / **MockDeterministicBackendV2** — Canned JSON responses for tests; no API.

So you do **not** need `OPENAI_API_KEY` or any `.env` for normal use. To run benchmarks with a **live** LLM: use `labtrust run-benchmark --llm-backend openai_live` or `openai_responses` (requires `OPENAI_API_KEY`; install `.[llm_openai]`), `--llm-backend anthropic_live` (requires `ANTHROPIC_API_KEY`; install `.[llm_anthropic]`), or `--llm-backend ollama_live` (local Ollama; set `LABTRUST_LOCAL_LLM_URL`, `LABTRUST_LOCAL_LLM_MODEL`, optionally `LABTRUST_LOCAL_LLM_TIMEOUT`). Live runs are non-deterministic. See [LLM baselines](llm_baselines.md) and [Live LLM benchmark mode](llm_live.md).

## Quick eval

After installing with `[env,plots]`, run a minimal sanity check (1 episode each of throughput_sla, adversarial_disruption, multi_site_stat with scripted baselines):

```bash
labtrust quick-eval
```

This:

1. Runs 1 episode of **throughput_sla** (scripted ops + runners), **adversarial_disruption** (with adversary), and **multi_site_stat** (throughput baseline).
2. Writes results and episode logs under `./labtrust_runs/quick_eval_<timestamp>/`.
3. Prints a markdown summary to stdout (throughput, violation count, blocked count per task).

Options:

- `--seed N` — Base seed for episodes (default: 42).
- `--out-dir DIR` — Output directory (default: `labtrust_runs`).

Example output:

```markdown
# LabTrust-Gym quick-eval

Run: 20250115_120000
Seed: 42
Tasks: throughput_sla, adversarial_disruption, multi_site_stat

| Task | Throughput | Violations | Blocked |
|------|------------|------------|--------|
| throughput_sla | 2 | 0 | 0 |
| adversarial_disruption | 1 | 0 | 0 |
| multi_site_stat | 1 | 0 | 0 |

Logs: `labtrust_runs/quick_eval_20250115_120000/logs`
```

On a clean machine (e.g. CI), `pip install labtrust-gym[env,plots]` followed by `labtrust quick-eval` should complete without errors. The CI pipeline runs quick-eval on every push/PR (see [CI](ci.md)).

## Development (editable install)

From the repo root:

```bash
git clone https://github.com/fraware/LabTrust-Gym.git
cd LabTrust-Gym
pip install -e ".[dev,env,plots]"
labtrust validate-policy
pytest -q
```

Optional extras: `.[marl]` (Stable-Baselines3), `.[docs]` (MkDocs + mkdocstrings).

### PyTorch on AMD or CPU-only (no CUDA)

LabTrust-Gym does not require CUDA. If you use an **AMD** CPU (e.g. Ryzen with integrated Radeon) or any machine without an NVIDIA GPU, use a CPU-only PyTorch build. CUDA is NVIDIA-only.

**Conda users:** If `conda` is not found in your shell, open **Anaconda Prompt** or **Miniconda Prompt** from the Start Menu so the conda base path is in PATH.

#### Conda environment with CPU-only PyTorch (recommended on Windows / AMD)

Create a dedicated conda environment with Python 3.12 and install PyTorch (CPU-only) from the pytorch channel, then install LabTrust-Gym into that environment:

```bash
conda create -n gym python=3.12 -y
conda activate gym
conda install pytorch torchvision torchaudio cpuonly -c pytorch
```

Then, from the LabTrust-Gym repo root, install the project and extras (pip will use the activated conda env):

```bash
cd LabTrust-Gym
pip install -e ".[dev,env,plots]"
# Optional, for MARL (PPO): pip install -e ".[dev,env,plots,marl]"
labtrust validate-policy
```

The conda env includes pip by default, so you do not need `ensurepip`. Use `conda activate gym` whenever you work on LabTrust-Gym with this setup.

#### Pip-only: CPU-only PyTorch

If you prefer a venv or system Python instead of conda:

- **Pip (venv or system):**
  ```bash
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
  ```

#### AMD GPU via DirectML (Windows, optional)

For hardware acceleration on AMD Radeon (or other non-NVIDIA) GPUs on Windows:

```bash
pip install torch-directml
```

This is the Windows alternative to CUDA for non-NVIDIA cards. Prefer the CPU-only build above if you do not need GPU acceleration.

#### Verify PyTorch

```python
import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available? {torch.cuda.is_available()}")  # False is correct for AMD/CPU-only
```

For MARL (PPO) and related tests, see [MARL baselines](marl_baselines.md).

**Quickstart (paper artifact):** From repo root, run `bash scripts/quickstart_paper_v0.1.sh` (or `scripts/quickstart_paper_v0.1.ps1` on Windows). Runs: install → validate-policy → quick-eval → package-release paper_v0.1 → verify-bundle. See [Frozen contracts](frozen_contracts.md) and [Paper-ready](paper_ready.md).

**UI export:** To produce a UI-ready zip from a run (quick-eval or package-release output): `labtrust ui-export --run <dir> --out ui_bundle.zip`. The bundle contains normalized `index.json`, `events.json`, `receipts_index.json`, and `reason_codes.json`. See [UI data contract](ui_data_contract.md).

## Troubleshooting

| Failure | Cause | Fix |
|--------|--------|-----|
| **ModuleNotFoundError: pettingzoo / gymnasium** | Missing `[env]` extra | `pip install labtrust-gym[env,plots]` or `pip install -e ".[env]"` |
| **labtrust: command not found** | Package not on PATH or not installed | Use `python -m labtrust_gym.cli.main` or reinstall with `pip install -e .` |
| **Policy file not found** | Policy path not resolved | Set `LABTRUST_POLICY_DIR` to repo `policy/` when developing; from wheel, policy is bundled. |
| **Schema validation failed** | Policy YAML/JSON doesn't match schema | Run `labtrust validate-policy`; fix reported files. For partner: `labtrust validate-policy --partner hsl_like`. |
| **Schema mismatch (results/receipt/UI bundle)** | Results or receipt schema version changed | Use schema version in file (`schema_version` / `ui_bundle_version`); UI and tools should ignore unknown optional fields (extensible-only policy). See [Frozen contracts](frozen_contracts.md) and [UI data contract](ui_data_contract.md). |
| **quick-eval / run-benchmark fails** | Missing env or plots | Install with `[env,plots]`: `pip install labtrust-gym[env,plots]`. |
| **MARL / train-ppo fails** | Missing `[marl]` | `pip install -e ".[marl]"` (Stable-Baselines3). |
| **MkDocs build fails** | Missing `[docs]` | `pip install -e ".[docs]"`. |
| **Path resolution (Windows)** | Spaces in path | Quote paths: `labtrust quick-eval --out-dir "C:\LabTrust runs"`. |
| **Set-Location / command "fails" (PowerShell)** | Project path contains **special characters** (e.g. **é** in "Matéo") | PowerShell or the runner may mangle Unicode and `cd` to the project dir can fail. **Fix:** Clone or move the repo to a path **without** accented characters (e.g. `C:\LabTrust-Gym`). Then run commands from that directory. Alternatively run from an existing shell already in the repo: `python -m labtrust_gym.cli.main --version`. |
| **pytest timeout** | Long test (e.g. `test_package_release_determinism`) runs full package-release | Run with a higher per-test timeout, e.g. `pytest -q --timeout=300`, or exclude long tests: `pytest -q --ignore=tests/test_package_release.py`. |
| **Security suite 0/10 passed** | pettingzoo/gymnasium or pytest missing in the env that runs `labtrust`; on Windows, `pip` may target global Python | Use the copy-paste command from the CLI hint (full path to venv Python). See [Security attack suite](security_attack_suite.md#prerequisites). |
| **No module named pip** (when running the venv’s `python -m pip`) | The venv was created without pip or pip was removed | Bootstrap pip: `& ".venv\Scripts\python.exe" -m ensurepip --upgrade` (PowerShell; use your venv path). Then run the `pip install` command again. |
