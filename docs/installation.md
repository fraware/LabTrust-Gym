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

If you want to use a `.env` file (e.g. for local overrides), load it yourself before running (e.g. `python-dotenv` in a wrapper script, or `export $(grep -v '^#' .env | xargs)` in bash before `labtrust`).

### LLMs: no API keys required by default

The **LLM baselines** (benchmarks, tests, quick-eval) do **not** call any external API by default. They use **deterministic, offline backends**:

- **DeterministicConstrainedBackend** — Official LLM baseline: chooses from allowed actions with a **seeded RNG**; no network, no API key.
- **MockDeterministicBackend** / **MockDeterministicBackendV2** — Canned JSON responses for tests; no API.

So you do **not** need `OPENAI_API_KEY` or any `.env` for normal use. To run benchmarks with a **live** LLM (e.g. OpenAI), use `labtrust run-benchmark --llm-backend openai_live`; then `OPENAI_API_KEY` is required. Those runs are non-deterministic and incur API cost. See [LLM baselines](llm_baselines.md) and [Live LLM benchmark mode](llm_live.md).

## Quick eval

After installing with `[env,plots]`, run a minimal sanity check (1 episode each of TaskA, TaskD, TaskE with scripted baselines):

```bash
labtrust quick-eval
```

This:

1. Runs 1 episode of **TaskA** (scripted ops + runners), **TaskD** (with adversary), and **TaskE** (throughput baseline).
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
Tasks: TaskA, TaskD, TaskE

| Task | Throughput | Violations | Blocked |
|------|------------|------------|--------|
| TaskA | 2 | 0 | 0 |
| TaskD | 1 | 0 | 0 |
| TaskE | 1 | 0 | 0 |

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

**Quickstart (paper artifact):** From repo root, run `bash scripts/quickstart_paper_v0.1.sh` (or `scripts/quickstart_paper_v0.1.ps1` on Windows). Runs: install → validate-policy → quick-eval → package-release paper_v0.1 → verify-bundle. See [CONTRACTS](CONTRACTS.md) and [Paper-ready](paper_ready.md).

**UI export:** To produce a UI-ready zip from a run (quick-eval or package-release output): `labtrust ui-export --run <dir> --out ui_bundle.zip`. The bundle contains normalized `index.json`, `events.json`, `receipts_index.json`, and `reason_codes.json`. See [UI data contract](ui_data_contract.md).

## Troubleshooting

| Failure | Cause | Fix |
|--------|--------|-----|
| **ModuleNotFoundError: pettingzoo / gymnasium** | Missing `[env]` extra | `pip install labtrust-gym[env,plots]` or `pip install -e ".[env]"` |
| **labtrust: command not found** | Package not on PATH or not installed | Use `python -m labtrust_gym.cli.main` or reinstall with `pip install -e .` |
| **Policy file not found** | Policy path not resolved | Set `LABTRUST_POLICY_DIR` to repo `policy/` when developing; from wheel, policy is bundled. |
| **Schema validation failed** | Policy YAML/JSON doesn't match schema | Run `labtrust validate-policy`; fix reported files. For partner: `labtrust validate-policy --partner hsl_like`. |
| **Schema mismatch (results/receipt/UI bundle)** | Results or receipt schema version changed | Use schema version in file (`schema_version` / `ui_bundle_version`); UI and tools should ignore unknown optional fields (extensible-only policy). See [CONTRACTS](CONTRACTS.md) and [UI data contract](ui_data_contract.md). |
| **quick-eval / run-benchmark fails** | Missing env or plots | Install with `[env,plots]`: `pip install labtrust-gym[env,plots]`. |
| **MARL / train-ppo fails** | Missing `[marl]` | `pip install -e ".[marl]"` (Stable-Baselines3). |
| **MkDocs build fails** | Missing `[docs]` | `pip install -e ".[docs]"`. |
| **Path resolution (Windows)** | Spaces in path | Quote paths: `labtrust quick-eval --out-dir "C:\LabTrust runs"`. |
| **Set-Location / command "fails" (PowerShell)** | Project path contains **special characters** (e.g. **é** in "Matéo") | PowerShell or the runner may mangle Unicode and `cd` to the project dir can fail. **Fix:** Clone or move the repo to a path **without** accented characters (e.g. `C:\LabTrust-Gym`). Then run commands from that directory. Alternatively run from an existing shell already in the repo: `python -m labtrust_gym.cli.main --version`. |
| **pytest timeout** | Long test (e.g. `test_package_release_determinism`) runs full package-release | Run with a higher per-test timeout, e.g. `pytest -q --timeout=300`, or exclude long tests: `pytest -q --ignore=tests/test_package_release.py`. |
