# Determinism contract (deterministic pipeline)

This document states what the deterministic pipeline guarantees and what it does not, so that baseline regression, reproducibility, and CI behavior are unambiguous.

## Guarantee

For a run with:

- **Same task** (e.g. throughput_sla, coord_scale)
- **Same base_seed** and **same number of episodes** (seeds = base_seed, base_seed+1, ...)
- **Same policy** (same repo state: policy files, schemas, key registry, equipment registry)
- **Same Python version** and **same platform** (when comparing file or log hashes)
- **Same timing_mode** (explicit or simulated)
- **Same coordination method** (for coord_scale/coord_risk) and **same injection** (for coord_risk)
- **Deterministic pipeline** (no LLM, or llm_backend deterministic/llm_offline only)

the following hold:

1. **Episode log**: The episode log (JSONL) is byte-identical. Its SHA-256 is reproducible.
2. **Results JSON**: The results file is written in **canonical form** (sort_keys=True, compact separators). The file content is byte-identical; its SHA-256 is reproducible.
3. **v0.2 metrics**: The normalized v0.2 representation (task, seeds, agent_baseline_id, episodes with seed + metrics) is identical. The baseline regression guard compares exact integer/struct metrics (throughput, steps, holds_count, tokens_minted, tokens_consumed, blocked_by_reason_code, violations_by_invariant_id).
4. **Receipts bundle**: When export_receipts is run on the same episode log, the manifest (and bundle root hash) is identical.

So: **same inputs => same outputs**. No global RNG; all randomness is derived from the per-episode seed (base_seed + episode index). Task initial state and engine each use a dedicated RNG seeded with that episode seed.

## Out of scope (no guarantee)

- **Cross-version**: Different Python versions (e.g. 3.11 vs 3.13) may use different RNG or float behavior. Do not assume identical hashes or float metrics across versions; prefer same Python version for baseline comparison.
- **Cross-platform**: Different OS (e.g. win32 vs linux) can differ in floating-point or dict iteration in edge cases. Baseline regression compares only integer and struct metrics to avoid float/platform sensitivity.
- **LLM or network**: The deterministic pipeline does not invoke any LLM or network. For live-LLM runs, non_deterministic is true and results are not byte-reproducible.

## Implementation notes

- **RNG**: Simulation uses `labtrust_gym.engine.rng.RNG`, which wraps `random.Random(seed)`. Task `get_initial_state(seed)` uses `random.Random(seed)` per call. No module-level or global RNG is used in the deterministic path.
- **Canonical write**: When `non_deterministic` is false, the runner writes results with `canonical_json(results)` (see `util.json_utils.canonical_json`) so the file is stable across runs. When non_deterministic is true, results are written with indent=2 for readability.
- **Determinism report**: `labtrust determinism-report` runs the benchmark twice in separate temp dirs with identical args and asserts episode log SHA-256, results canonical SHA-256, v0.2 metrics canonical, and (when available) receipts bundle root hash are identical. The report includes python_version and platform so that reproducibility is auditable.

## Commands

- **Prove determinism**: `labtrust determinism-report --task throughput_sla --episodes 3 --seed 42 --out ./det_report`
- **Baseline regression** (exact metrics vs committed v0.2): `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v`
- **Regenerate baselines** (after intentional changes): `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force`

See [Evaluation checklist](evaluation_checklist.md) and [Benchmarks](benchmarks.md).
