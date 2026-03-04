# Installation

## Pip (PyPI)

Install the package with optional extras for the environment and plots:

```bash
pip install labtrust-gym[env,plots]
```

- **env**: PettingZoo and Gymnasium (required for benchmarks and quick-eval).
- **plots**: Matplotlib (for study figures and data tables).

**Minimal install:** `pip install labtrust-gym` (no extras) supports policy validation (`labtrust validate-policy`) and the security suite in agent/shield-only mode if you use `--skip-system-level` (no PZ env). For scenario_ref and llm_attacker you still need dependencies used by the agent; see [Security attack suite](../risk-and-security/security_attack_suite.md).

**Full security suite:** To run all attack types including system-level coordination-under-attack (`coord_pack_ref`), install `pip install labtrust-gym[env]` (and optionally `[plots]` for other commands).

**Optional extras and test skips:** Installing extras reduces the number of tests and commands that skip. Use `pip install -e ".[full]"` to pull env, marl, docs, and plots in one go and minimize skips for local development.

| Extra | Reduces skips / enables |
|-------|--------------------------|
| `[env]` | PettingZoo/Gymnasium; coordination and security suite (system-level); quick-eval |
| `[dotenv]` | No-op (`.env` loading is now a default dependency) |
| `[plots]` | Study figures and data tables |
| `[marl]` | PPO/MARL baselines; train_ppo / eval_ppo CLI |
| `[docs]` | MkDocs site build |
| `[full]` | env + marl + docs + plots (single install to minimize skips) |

Check version and optional git SHA:

```bash
labtrust --version
```

When installed from a wheel, policy files are bundled in the package (package data under `labtrust_gym`); policy is loaded from the package by default and no repo root is needed. When developing from source, policy is read from the repo `policy/` directory; the resolver walks upward from the current working directory (up to a limited depth) to find a directory containing `policy/emits/`, so you can run from the repo root or any subdirectory. You can override the policy location with the `LABTRUST_POLICY_DIR` environment variable (path to the policy directory). If `LABTRUST_POLICY_DIR` is set but the path does not exist or is not a directory, the CLI and tests raise **PolicyPathError** (from `labtrust_gym.errors`) with a clear message. If no policy directory is found, the error message suggests setting `LABTRUST_POLICY_DIR`, running from repo root (or a subdirectory of the repo), or installing from wheel. See [State of the art and limits](../reference/state_of_the_art_and_limits.md).

**Reuse without repo tree:** When using the installed package (wheel), policy is bundled and no repo root is needed. From source, run from repo root or any subdirectory of the repo, or set `LABTRUST_POLICY_DIR`.

**Benchmark-only workflow (no clone):** To run the official pack and compare results without cloning or forking: (1) `pip install labtrust-gym[env,plots]` (add extras as needed). (2) Run `labtrust run-official-pack --out <dir>`. Policy is loaded from the package by default. To use a specific released policy snapshot (e.g. from a release artifact), download the policy bundle from the release (e.g. `policy-bundle-vX.Y.Z.tar.gz` from the release workflow artifacts or release assets), extract to a directory, set `LABTRUST_POLICY_DIR` to that directory (the extracted directory must contain `emits/`, `schemas/`, etc.), then run `labtrust run-official-pack --out <dir>`. No clone required.

**Reproducibility:** For byte-identical baselines, use the same Python version and OS as CI; pin dependencies; avoid env vars that change behavior. See the [Determinism contract](../benchmarks/determinism_contract.md). Different Python versions or platforms can change RNG or float behavior.

### Paths with spaces or special characters

If your repo or policy path contains spaces or special characters, use quoted paths in scripts (e.g. `"C:\My Lab\LabTrust-Gym"`) or set `REPO_ROOT` / `LABTRUST_POLICY_DIR` in the environment. On Windows, avoid accented characters in the path; clone to a simple path like `C:\LabTrust-Gym` if needed. See [Recommended Windows setup](windows_setup.md) and [Forker guide](forkers.md).

## Configuration (environment variables and .env)

LabTrust-Gym configuration is via **environment variables** (set in your shell or CI). You do **not** need a `.env` file for normal use. See `.env.example` in the repo root for a list of optional variables.

**Default .env loading:** The CLI loads a `.env` file at startup from the current working directory by default, or from the path in `LABTRUST_DOTENV_PATH` if set. Place a `.env` file (e.g. with `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) in the directory from which you run `labtrust` for live LLM and cross-provider demos.

Optional env vars (all have defaults or CLI overrides):

| Variable | Purpose |
|----------|---------|
| `LABTRUST_POLICY_DIR` | Path to policy directory (overrides package/repo policy). Must exist and be a directory or the CLI raises PolicyPathError. |
| `LABTRUST_PARTNER` | Partner overlay ID (e.g. `hsl_like`); same as `--partner` on CLI. |
| `LABTRUST_STRICT_SIGNATURES` | Set to `1` to enable strict signature verification in the engine. |
| `LABTRUST_STRICT_REASON_CODES` | Set to `1` so golden runner requires reason codes in registry. |
| `LABTRUST_REPRO_SMOKE` | Set to `1` / `true` / `yes` for reproduce/study smoke (1 episode per condition). |
| `LABTRUST_PAPER_SMOKE` | Set to `1` / `true` / `yes` for package-release paper_v0.1 smoke (few episodes). |
| `LABTRUST_RUN_GOLDEN` | Set to `1` to run full golden suite in tests (e.g. `pytest test_golden_suite.py`). |
| `LABTRUST_LOCAL_LLM_URL` | Base URL for local LLM (e.g. Ollama). Used when `--llm-backend ollama_live`. Default: `http://localhost:11434`. |
| `LABTRUST_LOCAL_LLM_MODEL` | Model name for local LLM (e.g. `llama3.2`). Used when `--llm-backend ollama_live`. |
| `LABTRUST_LOCAL_LLM_TIMEOUT` | Request timeout in seconds for local LLM. Default: 60. |
| `LABTRUST_DOTENV_PATH` | Path to `.env` file to load (default: `.env` in cwd). |

### Loading a .env file (optional)

If you run the CLI from a different directory than where your `.env` file lives, set `LABTRUST_DOTENV_PATH` to the full path of the `.env` file, or load it in your shell before running:

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

So you do **not** need `OPENAI_API_KEY` or any `.env` for normal use. To run benchmarks with a **live** LLM: use `labtrust run-benchmark --llm-backend openai_live` or `openai_responses` (requires `OPENAI_API_KEY`; install `.[llm_openai]`), `--llm-backend anthropic_live` (requires `ANTHROPIC_API_KEY`; install `.[llm_anthropic]`), or `--llm-backend ollama_live` (local Ollama; set `LABTRUST_LOCAL_LLM_URL`, `LABTRUST_LOCAL_LLM_MODEL`, optionally `LABTRUST_LOCAL_LLM_TIMEOUT`). Live runs are non-deterministic. See [LLM baselines](../agents/llm_baselines.md) and [Live LLM benchmark mode](../agents/llm_live.md).

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

On a clean machine (e.g. CI), `pip install labtrust-gym[env,plots]` followed by `labtrust quick-eval` should complete without errors. The CI pipeline runs quick-eval on every push/PR (see [CI](../operations/ci.md)).

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

For MARL (PPO) and related tests, see [MARL baselines](../agents/marl_baselines.md).

**Quickstart (paper artifact):** From repo root, run `bash scripts/quickstart_paper_v0.1.sh` (or `scripts/quickstart_paper_v0.1.ps1` on Windows). Runs: install → validate-policy → quick-eval → package-release paper_v0.1 → verify-bundle. See [Frozen contracts](../contracts/frozen_contracts.md) and [Paper provenance](../benchmarks/paper/README.md).

**UI export:** To produce a UI-ready zip from a run (quick-eval or package-release output): `labtrust ui-export --run <dir> --out ui_bundle.zip`. The bundle contains normalized `index.json`, `events.json`, `receipts_index.json`, and `reason_codes.json`. See [UI data contract](../contracts/ui_data_contract.md).

## Troubleshooting

| Failure | Cause | Fix |
|--------|--------|-----|
| **ModuleNotFoundError: pettingzoo / gymnasium** | Missing `[env]` extra | `pip install labtrust-gym[env,plots]` or `pip install -e ".[env]"` |
| **labtrust: command not found** | Package not on PATH or not installed | Use `python -m labtrust_gym.cli.main` or reinstall with `pip install -e .` |
| **Policy file not found** | Policy path not resolved | Set `LABTRUST_POLICY_DIR` to repo `policy/` when developing; from wheel, policy is bundled. |
| **Schema validation failed** | Policy YAML/JSON doesn't match schema | Run `labtrust validate-policy`; fix reported files. For partner: `labtrust validate-policy --partner hsl_like`. |
| **Schema mismatch (results/receipt/UI bundle)** | Results or receipt schema version changed | Use schema version in file (`schema_version` / `ui_bundle_version`); UI and tools should ignore unknown optional fields (extensible-only policy). See [Frozen contracts](../contracts/frozen_contracts.md) and [UI data contract](../contracts/ui_data_contract.md). |
| **quick-eval / run-benchmark fails** | Missing env or plots | Install with `[env,plots]`: `pip install labtrust-gym[env,plots]`. |
| **MARL / train-ppo fails** | Missing `[marl]` | `pip install -e ".[marl]"` (Stable-Baselines3). |
| **MkDocs build fails** | Missing `[docs]` | `pip install -e ".[docs]"`. |
| **Path resolution (Windows)** | Spaces in path | Quote paths: `labtrust quick-eval --out-dir "C:\LabTrust runs"`. |
| **Set-Location / command "fails" (PowerShell)** | Project path contains **special characters** (e.g. **é** in "Matéo") | PowerShell or the runner may mangle Unicode and `cd` to the project dir can fail. **Fix:** Clone or move the repo to a path **without** accented characters (e.g. `C:\LabTrust-Gym`). Then run commands from that directory. Alternatively run from an existing shell already in the repo: `python -m labtrust_gym.cli.main --version`. |
| **pytest timeout** | Long test (e.g. `test_package_release_determinism`) runs full package-release | Run with a higher per-test timeout, e.g. `pytest -q --timeout=300`, or exclude long tests: `pytest -q --ignore=tests/test_package_release.py`. |
| **Security suite 0/10 passed** | pettingzoo/gymnasium or pytest missing in the env that runs `labtrust`; on Windows, `pip` may target global Python | Use the copy-paste command from the CLI hint (full path to venv Python). See [Security attack suite](../risk-and-security/security_attack_suite.md#prerequisites). |
| **No module named pip** (when running the venv’s `python -m pip`) | The venv was created without pip or pip was removed | Bootstrap pip: `& ".venv\Scripts\python.exe" -m ensurepip --upgrade` (PowerShell; use your venv path). Then run the `pip install` command again. |
| **CLI exits with error (unclear message)** | Invalid args, missing policy, or env | Run `labtrust <command> --help` for usage; run `labtrust validate-policy` to check policy. Ensure `LABTRUST_POLICY_DIR` points to repo `policy/` when developing from source. |
