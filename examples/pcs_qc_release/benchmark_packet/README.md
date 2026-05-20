# LabTrust QC release benchmark packet

Minimal two-case packet for `pcs-bench` smoke runs without loading the full failure gallery.

| Directory | Role |
|-----------|------|
| `valid_release/` | Positive control (passes release protocol verification) |
| `invalid_trace_hash_tamper/` | Symlink-style layout: copy of `trace_hash_tamper` gallery case |

Each case directory contains `benchmark_case.v0.json`, `labtrust_benchmark_extension.v0.json`, `input_artifacts/`, `expected_failure.json`, and `expected_repair_hint.json`.

## Regenerate

From the repository root:

```bash
python examples/pcs_qc_release/scripts/generate_benchmark_packet.py
```

On Unix:

```bash
bash examples/pcs_qc_release/benchmark_packet/reproduce.sh
```

## pcs-bench

Point `pcs-bench` at case roots under this packet, or use the committed suite under `examples/pcs_qc_release/benchmark/` for the full 13-case suite (`labtrust-qc-release-v0`).
