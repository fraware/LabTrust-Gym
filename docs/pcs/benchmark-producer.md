# PCS benchmark producer

LabTrust is the reference producer for the hospital lab QC release PCS benchmark. All
machine-readable outputs align with pcs-core v0 schemas and normalize into
`PcsBenchIngest.v0` for pcs-bench.

See [producer-contract.md](producer-contract.md) for release-grade gates, artifact ref roles, and pcs-bench validation paths.

## Producer surfaces

| Command | Output |
|---------|--------|
| `labtrust generate-benchmark-cases --pcs-bench-layout` | Case suite: `valid/`, `invalid/`, `suite.yaml`, `benchmark_manifest.v0.json`, `benchmark_task.v0.json` |
| `labtrust benchmark-reproducibility` | Run ingest: `pcs_bench_ingest.v0.json`, `benchmark_report.v0.json`, `benchmark_manifest.v0.json` |
| `labtrust verify-benchmark-cases --validate-pcs-core-output` | Schema gate (LabTrust + pcs-core) |

## Canonical refresh (pcs-bench)

```bash
labtrust generate-benchmark-cases \
  --workflow hospital_lab.qc_release \
  --out ../pcs-bench/benchmarks/labtrust_qc_release \
  --pcs-bench-layout \
  --seed 42 \
  --validate-pcs-core-output ../pcs-core

cd ../pcs-bench
pcs-bench validate-cases --suite labtrust-qc-release --pcs-core ../pcs-core
```

Publish into pcs-core registry (optional):

```bash
python examples/pcs_qc_release/scripts/generate_pcs_bench_suite.py \
  --out ../pcs-core/benchmarks/labtrust-qc-release \
  --registry ../pcs-core/examples/benchmark_registry.valid.json \
  --validate-pcs-core-output ../pcs-core
```

## Reproducibility ingest

```bash
make pcs-bench-producer
```

Windows: `.\scripts\pcs_bench_producer.ps1`

Equivalent manual flow:

```bash
labtrust benchmark-reproducibility \
  --workflow hospital_lab.qc_release \
  --mode full_regeneration \
  --pcs-core ../pcs-core \
  --certifyedge-bin certifyedge \
  --runs 5 \
  --out benchmark_runs/labtrust_reproducibility \
  --validate-pcs-core-output ../pcs-core \
  --release-grade

pcs-bench validate-ingest \
  --input benchmark_runs/labtrust_reproducibility/pcs_bench_ingest.v0.json \
  --pcs-core ../pcs-core
```

Release-grade mode requires `full_regeneration`, CertifyEdge success rate 1.0, and per-run
release-protocol, status-policy, and pcs-core validation. `workflow_id` is always
`hospital_lab.qc_release`.

## Validation layers

1. LabTrust schemas under `policy/schemas/pcs/`
2. pcs-core cross-schema validation when `--validate-pcs-core-output` is set
3. CI scripts under `examples/pcs_qc_release/scripts/ci_validate_*`

## Smoke fixtures

| Path | Purpose |
|------|---------|
| `examples/pcs_qc_release/benchmark_packet/` | Two-case smoke packet |
| `tests/fixtures/pcs_bench_reproducibility/` | Offline producer tree (`make pcs-fixtures`) |
| `examples/pcs_qc_release/benchmark_ingest/golden/` | Optional ingest golden |

See [benchmark-profile.md](benchmark-profile.md) for taxonomy and metrics.
