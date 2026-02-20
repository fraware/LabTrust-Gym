# Paper figure and table provenance (v0.1.0)

Figure/table to path, command, and seeds. Aligned with [PAPER_CLAIMS](../PAPER_CLAIMS.md). Update when the paper is written.

## Provenance map

| Figure / table | Path (in package-release or repo) | Command | Seeds |
|----------------|-----------------------------------|--------|-------|
| **Figure 1** (throughput vs violations Pareto) | `FIGURES/throughput_vs_violations_pareto.png` | `labtrust make-plots --run <study_out>` (from run-study below) | study: default in spec |
| **Figure 2** (trust cost vs p95 TAT) | `FIGURES/trust_cost_vs_p95_tat_pareto.png` | same | same |
| **Table 1** (summary by condition) | `TABLES/paper_table.md` or `summary.csv` | same; `make-plots` writes TABLES/ | same |
| **Official baseline table** | `benchmarks/baselines_official/v0.2/summary_v0.2.csv` | Pre-generated; or `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 200 --seed 123` | `--seed 123` |

**Study:** `labtrust run-study --spec policy/studies/trust_ablations.v0.1.yaml --out <dir>`. **Plots:** `labtrust make-plots --run <dir>`.

**Paper-ready artifact (all figures/tables):** `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>`. Seeds: `seed_base=100` (and per-step offsets as in the profile). Verification: `labtrust verify-bundle --bundle <dir>/receipts/.../EvidenceBundle.v0.1` or `labtrust verify-release --release-dir <dir>`.

## Paper tarball

A single tarball (e.g. from GitHub Release or Zenodo) should contain or point to:

- Wheel/sdist: `pip install labtrust-gym[env,plots]`
- Policy: bundled in wheel or `policy/` in repo
- This provenance map: `docs/paper/README.md`
- CONTRACTS: `docs/frozen_contracts.md`
- PAPER_CLAIMS: `docs/PAPER_CLAIMS.md`

Verification: run quick-eval, package-release paper_v0.1, verify-bundle on the produced bundle.

## Reference demonstration

The paper profile is the **reference demonstration** for external reviewers: the same commands, seeds, and verification steps produce identical artifacts so anyone can "see the tools in action" and reproduce the result.

1. Build the paper-ready artifact: `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>`
2. Verify the release: `labtrust verify-release --release-dir <dir> --strict-fingerprints`

**Success:** `verify-release` exits 0; all EvidenceBundles and RELEASE_MANIFEST validate. See [Quick demos](../getting-started/quick_demos.md) and [Release checklist](../operations/release_checklist.md).
