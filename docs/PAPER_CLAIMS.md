# Paper claims and citation-grade reproducibility (v0.1.0)

Which tasks/baselines are official, which metrics are claimed, and where the numbers come from (file paths).

## Official tasks and baselines

| Task | Description | Official baseline |
|------|-------------|-------------------|
| TaskA | Throughput under SLA | scripted_ops_v1 |
| TaskB | STAT insertion under load | scripted_ops_v1 |
| TaskC | QC fail cascade | scripted_ops_v1 |
| TaskD | Adversarial disruption | adversary_v1 |
| TaskE | Multi-site STAT | scripted_ops_v1 |
| TaskF | Insider and key misuse | insider_v1 |

Registry: `benchmarks/baseline_registry.v0.1.yaml`. Regenerate with `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force`.

## Claimed metrics and file paths

| Metric | File path (in release artifact) |
|--------|---------------------------------|
| Throughput (mean/std) | summary_v0.2.csv (throughput_mean, throughput_std) |
| p95 TAT | summary_v0.2.csv (p95_turnaround_s_mean, p95_turnaround_s_std) |
| Violations | results/*.json episodes[].metrics.violations_by_invariant_id |
| Official baseline table | benchmarks/baselines_official/v0.2/summary_v0.2.csv |

## Reproducing from a release tarball

1. pip install labtrust-gym[env,plots]
2. labtrust validate-policy
3. labtrust quick-eval --seed 42
4. labtrust package-release --profile paper_v0.1 --seed-base 100 --out dir
5. labtrust verify-bundle --bundle dir/EvidenceBundle.v0.1

See CONTRACTS.md and reproduce.md. Optional: Zenodo DOI for v0.1.0; add doi to CITATION.cff.
