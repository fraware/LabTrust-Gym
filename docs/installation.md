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
