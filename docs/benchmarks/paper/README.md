# Paper figure and table provenance (paper_v0.1 profile)

Figure/table to path, command, and seeds. Aligned with [PAPER_CLAIMS](../PAPER_CLAIMS.md). Update when the paper is written.

## Provenance map

| Figure / table | Path (in package-release or repo) | Command | Seeds |
|----------------|-----------------------------------|--------|-------|
| **Throughput vs violations** (Pareto) | `FIGURES/throughput_vs_violations.png` (and `.svg`) | `labtrust package-release --profile paper_v0.1 --out <dir>` (plots from _study via make_plots) | study: seed_base (default 100) |
| **Trust cost vs p95 TAT** | `FIGURES/trust_cost_vs_p95_tat.png` (and `.svg`) | same | same |
| **Throughput box by condition** | `FIGURES/throughput_box_by_condition.png` | same | same |
| **Metrics overview** (dashboard) | `FIGURES/metrics_overview.png` | same | same |
| **Table 1** (summary by condition) | `TABLES/summary.csv`, `TABLES/summary.md`, `TABLES/paper_table.md` | same; paper profile runs summarize over _baselines + _study | same |
| **Official baseline table** (canonical) | `benchmarks/baselines_official/v0.2/summary.csv` (or `summary_v0.2.csv`, `summary_v0.3.csv`) | Pre-generated; or `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 200 --seed 123 --force` | `--seed 123` |

**Paper profile (all-in-one):** `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>`. This runs: (1) `generate-official-baselines` into `<dir>/_baselines/`, (2) insider_key_misuse strict_signatures ablation study into `<dir>/_study/`, (3) summarize into `<dir>/TABLES/`, (4) representative runs and receipts per task, (5) SECURITY/, TRANSPARENCY_LOG/, SAFETY_CASE/, (6) `make_plots(_study)` → copies figures to `<dir>/FIGURES/`, (7) BENCHMARK_CARD, COORDINATION_CARD, MANIFEST.

**Standalone study + plots:** `labtrust run-study --spec <spec.yaml> --out <study_dir>` then `labtrust make-plots --run <study_dir>`. Example spec: `policy/studies/trust_ablations.v0.1.yaml` (throughput_sla trust/dual ablations) or the inline spec used by paper profile (insider_key_misuse, strict_signatures [False, True]).

**Verification:** `labtrust verify-bundle --bundle <dir>/receipts/<task>/EvidenceBundle.v0.1` per task, or `labtrust verify-release --release-dir <dir>` for the full release. For strict fingerprint checks: `labtrust verify-release --release-dir <dir> --strict-fingerprints`.

## Paper tarball

A single tarball (e.g. from GitHub Release or Zenodo) should contain or point to:

- Wheel/sdist: `pip install labtrust-gym[env,plots]`
- Policy: bundled in wheel or `policy/` in repo
- This provenance map: `docs/benchmarks/paper/README.md`
- CONTRACTS: `docs/contracts/frozen_contracts.md` (if present)
- PAPER_CLAIMS: `docs/benchmarks/PAPER_CLAIMS.md`

Verification: run quick-eval, package-release paper_v0.1, verify-release on the produced directory.

## Reference demonstration

The paper profile is the **reference demonstration** for external reviewers: the same commands, seeds, and verification steps produce identical artifacts so anyone can reproduce the result.

1. Build the paper-ready artifact: `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>`
2. Verify the release: `labtrust verify-release --release-dir <dir> --strict-fingerprints`

**Success:** `verify-release` exits 0; all EvidenceBundles and RELEASE_MANIFEST validate. See [Quick demos](../../getting-started/quick_demos.md) and [Trust verification](../../risk-and-security/trust_verification.md).
