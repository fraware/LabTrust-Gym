# PCS workflow template

Generic starter for a **protocol-native PCS workflow** (computation pipeline, tool-use agent, or
other domain). Copy this directory into your repo and replace placeholders.

## Layout

```text
workflow_profile.v0.json   # WorkflowProfile.v0 (edit handoffs, failure_modes, property_id)
workflow.py                # PCSWorkflow subclass (register in labtrust_gym.pcs.workflows.registry)
tests/test_workflow_skeleton.py
```

## Integration checklist

1. Fill `workflow_profile.v0.json` and materialize digests.
2. Implement `execute_runtime`, exporters, and `generate_failure_case` in `workflow.py`.
3. Register the class in `src/labtrust_gym/pcs/workflows/registry.py`.
4. Add `examples/<your_workflow>/` with scenarios, `release/`, and `failures/`.
5. Run `labtrust regenerate-release-protocol --out examples/<your_workflow>/release`.
6. Confirm `regeneration_report.json` status is `passed`.

See `docs/pcs-workflow-implementation-guide.md` for the five-layer PCS model and LabTrust QC
reference paths.
