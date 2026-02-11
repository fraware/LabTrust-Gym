# Paper figure and table provenance (v0.1.0)

Figure/table → path and command. Update when the paper is written.

## Provenance map

| Figure / table | Path (in package-release or repo) | Command |
|----------------|-----------------------------------|--------|
| **Figure 1** (throughput vs violations Pareto) | `FIGURES/throughput_vs_violations_pareto.png` | `labtrust make-plots --run <study_out>` (from `labtrust run-study --spec policy/studies/trust_ablations.v0.1.yaml`) |
| **Figure 2** (trust cost vs p95 TAT) | `FIGURES/trust_cost_vs_p95_tat_pareto.png` | same |
| **Table 1** (summary by condition) | `TABLES/paper_table.md` or `summary.csv` | same; `make-plots` writes TABLES/ |
| **Official baseline table** | `benchmarks/baselines_official/v0.2/summary_v0.2.csv` | Pre-generated; or `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 200 --seed 123` |

Study spec: `policy/studies/trust_ablations.v0.1.yaml`. Run study: `labtrust run-study --spec policy/studies/trust_ablations.v0.1.yaml --out <dir>`. Plots: `labtrust make-plots --run <dir>`.

## Paper tarball

A single tarball (e.g. from GitHub Release or Zenodo) should contain or point to:

- Wheel/sdist: `pip install labtrust-gym[env,plots]`
- Policy: bundled in wheel or `policy/` in repo
- This provenance map: `docs/paper/README.md`
- CONTRACTS: `docs/frozen_contracts.md`
- PAPER_CLAIMS: `docs/PAPER_CLAIMS.md`

Verification: run quick-eval, package-release paper_v0.1, verify-bundle on the produced bundle.
