# Official baselines v0.1

Frozen benchmark results for a fixed seed set, used for leaderboard comparison.

- **results/**: Frozen `results.json` outputs (or symlinks to package-release artifact).
- **summary.csv**, **summary.md**: Wide table (mean/std for throughput, TAT, on_time_rate, violations, critical compliance, detection_latency, containment_success) grouped by task + baseline + partner_id. Generate with:
  ```bash
  labtrust summarize-results --in results/ --out . --basename summary
  ```
- **metadata.json**: git_sha, policy_fingerprint, package-release manifest hash, seed_set, tasks.

To compare your run to the official baseline:

```bash
labtrust summarize-results --in benchmarks/baselines_official/v0.1/results/ your_results.json --out /tmp/compare --basename comparison
```

See [Benchmark card](../../../docs/benchmark_card.md) and README for the official baseline table.
