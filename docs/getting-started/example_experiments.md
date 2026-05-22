# Example experiments

The following experiments illustrate how trust mechanisms (trust skeleton, dual approval, strict signatures) affect behaviour and performance. All commands are reproducible with fixed seeds.

## Experiment 1: Trust skeleton and dual approval

Run the following command.

```bash
labtrust reproduce --profile minimal
```

Use `--profile full` for more episodes per condition. Set a custom output directory with `--out runs/my_repro`.

This experiment varies `trust_skeleton` [on, off] × `dual_approval` [on, off], giving four conditions per task. See [Reproduce](../benchmarks/reproduce.md).

Compare throughput and violations across conditions. Figures and data tables live under:

- `runs/repro_minimal_<timestamp>/taska/figures/` and `taska/figures/data_tables/`
- `runs/repro_minimal_<timestamp>/taskc/figures/` and `taskc/figures/data_tables/`

Example figures include `throughput_vs_violations.png`, `trust_cost_vs_p95_tat.png`, `violations_by_invariant_id.png`, and `blocked_by_reason_code_top10.png`.

With the trust skeleton on and dual approval where required, the engine enforces invariants and blocks unsafe actions (BLOCKED + reason codes). With trust off, violations can increase. Trust adds control and auditability at the cost of extra checks.

Output is written to `runs/repro_minimal_<timestamp>/`, or to the path you pass with `--out`.

---

## Experiment 2: Strict signatures and containment (insider_key_misuse)

Run the following command.

```bash
labtrust package-release --profile paper_v0.1 --seed-base 100 --out release_paper
```

To run only the insider study (skip the full release):

```bash
labtrust run-study --spec policy/studies/study_spec.taskf_insider.v0.1.yaml --out <dir>
```

This experiment varies `strict_signatures` [false, true] across insider attack phases (RBAC deny, forged signature, replay, token misuse).

In the study results, compare:

- `fraction_of_attacks_contained`
- `time_to_first_detected_security_violation`
- `forensic_quality_score`

See [Benchmarks](../benchmarks/benchmarks.md) (insider_key_misuse) for metric definitions.

With `strict_signatures: true`, forged and replayed signatures are BLOCKED (SIG_INVALID). With `strict_signatures: false`, the simulator may accept them. Enable the signature trust mechanism to achieve containment and forensic quality.

For the paper profile, outputs appear under `<dir>/_study/`, `TABLES/`, and `FIGURES/`. For a study-only run, use `<dir>/results/cond_*/` and `figures/`.

---

## Experiment 3 (optional): Quick baseline

Run the following command.

```bash
labtrust quick-eval --seed 42
```

This runs one episode each of throughput_sla, adversarial_disruption, and multi_site_stat with scripted baselines.

You get baseline performance and metrics (throughput, violations, blocked counts) with the default trust skeleton, which is a useful reference before running reproduce or paper experiments.

---

## Reproducibility

- **Seeding and determinism** — Same seed, same code, and same policy yield the same results. See [Reproduce](../benchmarks/reproduce.md) for seeding and study manifests.
- **Paper profile and study specs** — See [Paper provenance](../benchmarks/paper/README.md) for the paper_v0.1 profile and figure/table provenance.
