# Example: custom coordination method only

Minimal extension that registers a single **coordination method** via the `labtrust_gym.coordination_methods` entry point. No new task is defined; use an existing task (e.g. `coord_scale` or `coord_risk`) with `--coord-method example_noop_coord`.

## Install

From repo root:

```bash
pip install -e examples/coord_method_example
```

## Run

```bash
labtrust run-benchmark --task coord_scale --coord-method example_noop_coord --scale small_smoke --episodes 1 --out results.json
```

The method `example_noop_coord` returns NOOP for all agents every step (minimal behaviour for demonstration). Replace with your own logic in `src/example_coord_plugin/method.py` and implement `CoordinationMethod` (see [Extension development](../../docs/agents/extension_development.md) and `labtrust_gym.baselines.coordination.interface`).

## Contract

- **Entry point:** `labtrust_gym.coordination_methods` with name `example_noop_coord` and a **factory** callable `(policy, repo_root, scale_config_override, default_params) -> CoordinationMethod`.
- **CoordinationMethod:** Must implement `method_id` (property) and `propose_actions(obs, infos, t)` returning one action dict per agent (see interface and policy schema).
