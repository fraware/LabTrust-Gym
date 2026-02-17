# Official baselines v0.2 (canonical)

This directory is the **canonical frozen baseline set** for the baseline regression guard. From LabTrust-Gym; cite the repository and the regenerate command below for reproducibility.

- **results/** — One `<task>_<baseline>.json` per task: throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse, coord_scale, coord_risk (schema v0.2). Generated with `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123`.
- **summary_v0.2.csv**, **summary_v0.3.csv**, **summary.csv**, **summary.md** — Aggregated summary tables (from summarize-results).
- **metadata.json** — Version, git_sha, cli_args (episodes, seed, timing), tasks, baseline_ids.

The baseline regression test (`LABTRUST_CHECK_BASELINES=1`) runs benchmarks with episodes=3, seed=123, timing=explicit and compares exact integer/struct metrics to these files. Do not change v0.2 semantics; to refresh, run:

```bash
labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force
```

**v0.1** in this repo is legacy; regression uses v0.2 only.
