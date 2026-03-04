# Minimal extension example

Install with `pip install -e .` from this directory. Then from the LabTrust-Gym repo root run:

```bash
labtrust --profile example run-benchmark --task example_task --episodes 1
```

This requires a lab profile that lists this package in `extension_packages` (e.g. `policy/lab_profiles/example.v0.1.yaml` in the main repo with `extension_packages: ["example-plugin"]`). You also need `.[env]` installed in the main repo for run-benchmark.

Copy this directory to start your own plugin. The only supported contract for new tasks is `BenchmarkTask`; see [Extension development](https://github.com/fraware/LabTrust-Gym/blob/main/docs/agents/extension_development.md) and [Public API](https://github.com/fraware/LabTrust-Gym/blob/main/docs/reference/public_api.md).
