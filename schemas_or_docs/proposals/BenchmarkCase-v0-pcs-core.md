# Proposal: BenchmarkCase.v0 (pcs-core / pcs-bench)

## Summary

Promote LabTrust's `BenchmarkCase.v0` descriptor to pcs-core so `pcs-bench` can load any
workflow suite without per-repo adapters.

## Suggested pcs-core placement

- Schema: `schemas/BenchmarkCase.v0.schema.json`
- Suite index: `schemas/BenchmarkSuiteIndex.v0.schema.json` (extends LabTrust `benchmark_index.json`)
- Reproducibility: `schemas/BenchmarkRun.v0.schema.json`

## LabTrust reference

- Generator: `labtrust generate-benchmark-cases`
- Verifier: `labtrust verify-benchmark-cases`
- Suite: `examples/pcs_qc_release/benchmark/`
- Profile: [docs/labtrust-benchmark-profile.md](../../docs/labtrust-benchmark-profile.md)

## pcs-bench loader contract (`pcs_bench` block)

```json
{
  "pcs_bench": {
    "version": "v0",
    "case_descriptor": "benchmark_case.v0.json",
    "input_dir": "input_artifacts",
    "expected_failure": "expected_failure.json",
    "expected_repair_hint": "expected_repair_hint.json"
  }
}
```
