# How to add a new coordination method

Add a new coordination method so it appears in the pack matrix, study runner, and selection policy.

## 1. Policy

Add an entry to `policy/coordination/coordination_methods.v0.1.yaml` (or your partner overlay `policy/partners/<id>/coordination/coordination_methods.v0.1.yaml`). Follow the schema: `method_id`, `coordination_class` (e.g. `centralized`, `llm`, `market`), optional `default_params`, and other fields such as `known_weaknesses`, `required_controls`, `compatible_injections`. Example:

```yaml
- method_id: my_allocator
  name: "My custom allocator"
  coordination_class: centralized
  llm_based: false
  scaling_knobs: ["num_agents", "num_sites"]
  known_weaknesses: ["R-SYS-001"]
  required_controls: ["RBAC"]
  default_params:
    some_param: 0.5
```

Register the **method_id** in `src/labtrust_gym/baselines/coordination/registry.py`: add a factory mapping so `make_coordination_method(method_id, ...)` can instantiate your class. The registry maps `method_id` to a factory; the policy does not specify the Python class name.

- **Scale-capable:** If your method supports the combine path with per-agent LLM at N > coord_propose_actions_max_agents, add **scale_capable: true** to its entry in coordination_methods.v0.1.yaml; otherwise the runner will not populate scripted_agents_map with per-agent LLM for that method at scale.

## 2. Code

Implement the coordination interface (see `src/labtrust_gym/baselines/coordination/interface.py`): your class must implement the expected API (e.g. `propose_actions`, optional `step(context)` for kernel-composed methods, optional `combine_submissions`). Register your factory in `src/labtrust_gym/baselines/coordination/registry.py` so `method_id` maps to an instantiation path. See existing methods in the registry and under `src/labtrust_gym/baselines/coordination/` for the interface and registration pattern.

## 3. Tests

Add or extend tests so the new method is exercised:

- **Interface contract:** `tests/test_coordination_interface_contract.py` runs all registered methods for a short episode (coord_scale, 5 steps). Your method will be picked up if it is registered; ensure it does not raise or hang.
- **Pack smoke:** Running `labtrust run-coordination-security-pack --methods-from full` (or a path that includes your `method_id`) will include your method in the matrix. Add a small unit or integration test if the method has specific logic that needs coverage.

## 4. Pack and study matrix

- **Security pack:** The pack loads methods from policy (fixed set or full). If you use `--methods-from full`, your new method is included automatically when listed in the methods policy. For a custom list, use `--methods-from path/to/file` with one `method_id` per line (or YAML list).
- **Study spec:** To include the method in `run-coordination-study`, add its `method_id` to the spec’s `methods` list in `policy/coordination/coordination_study_spec.v0.1.yaml` (or partner overlay).

## 5. Conformance and SOTA checklist

To bring the method to the full SOTA bar:

- **Conformance:** When the method passes the budget and evidence contracts under the conformance scale_config (tight compute_budget_ms / compute_budget_node_expansions), add its `method_id` to `pass_budget` and `pass_evidence` in `tests/coord_methods/conformance/conformance_config.yaml`. Run the conformance matrix: `pytest tests/coord_methods/conformance/ -v`.
- **Strictly-better scenario:** Add at least one test in `tests/test_coord_strictly_better.py` that runs the same scale/seed/injection for a baseline and for your method, then asserts your method is at least as good on a chosen metric (e.g. throughput or violations). Use `_run_coord_one_episode` and `_throughput_from_results` (or `_violations_count_from_results`). For LLM methods use `pipeline_mode="llm_offline"` and `llm_backend="deterministic_constrained"` for CI.
- **Envelope:** Document compute/latency in a module or class docstring section "Envelope (SOTA audit)" (steps, llm_calls_per_step, fallback, max_latency_ms) and add a `# compute_envelope: ...` comment in the method's block in `policy/coordination/coordination_methods.v0.1.yaml`.

Run `python scripts/refresh_sota_checklist.py` from repo root for the per-method dashboard (pass_budget, pass_evidence, strictly-better test, envelope).

After adding the method, run `labtrust validate-policy` and at least the coordination interface contract test; then run a short pack or study to confirm the method appears and completes without error.
