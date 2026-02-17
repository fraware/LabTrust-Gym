# How to add a new coordination method

Add a new coordination method so it appears in the pack matrix, study runner, and selection policy.

## 1. Policy

Add an entry to `policy/coordination/coordination_methods.v0.1.yaml` (or your partner overlay `policy/partners/<id>/coordination/coordination_methods.v0.1.yaml`). Follow the schema: `method_id`, `class` (e.g. the Python class name used by the registry), and optional `config`. Example:

```yaml
- method_id: my_allocator
  class: MyAllocator
  config:
    some_param: 0.5
```

Ensure the `class` is registered in `src/labtrust_gym/baselines/coordination/registry.py` (or equivalent) so the runner can instantiate it.

## 2. Code

Implement the coordination interface (see `src/labtrust_gym/baselines/coordination/interface.py`): your class must implement the expected API (e.g. propose actions, consume step results). Add the class to the method registry so `method_id` maps to the class. See an existing method under `src/labtrust_gym/baselines/coordination/methods/` for the exact interface and registration pattern.

## 3. Tests

Add or extend tests so the new method is exercised:

- **Interface contract:** `tests/test_coordination_interface_contract.py` runs all registered methods for a short episode (coord_scale, 5 steps). Your method will be picked up if it is registered; ensure it does not raise or hang.
- **Pack smoke:** Running `labtrust run-coordination-security-pack --methods-from full` (or a path that includes your `method_id`) will include your method in the matrix. Add a small unit or integration test if the method has specific logic that needs coverage.

## 4. Pack and study matrix

- **Security pack:** The pack loads methods from policy (fixed set or full). If you use `--methods-from full`, your new method is included automatically when listed in the methods policy. For a custom list, use `--methods-from path/to/file` with one `method_id` per line (or YAML list).
- **Study spec:** To include the method in `run-coordination-study`, add its `method_id` to the spec’s `methods` list in `policy/coordination/coordination_study_spec.v0.1.yaml` (or partner overlay).

After adding the method, run `labtrust validate-policy` and at least the coordination interface contract test; then run a short pack or study to confirm the method appears and completes without error.
