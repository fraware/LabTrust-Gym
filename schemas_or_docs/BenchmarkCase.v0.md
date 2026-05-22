# BenchmarkCase.v0

Machine-readable PCS benchmark case for **pcs-bench**. Supersedes ad-hoc failure-gallery
metadata for benchmark runners while keeping gallery layouts for demos.

## Layout

```text
<benchmark_root>/<case_id>/
  benchmark_case.v0.json
  input_artifacts/
  expected_failure.json
  expected_repair_hint.json
  README.md
```

## Schema

`policy/schemas/pcs/BenchmarkCase.v0.schema.json`

## Generator

```bash
labtrust generate-benchmark-cases --out examples/pcs_qc_release/benchmark --seed 42
```

See [docs/pcs/benchmark-profile.md](../docs/pcs/benchmark-profile.md).
