# Example experiments

The following experiments illustrate how trust mechanisms (trust skeleton, dual approval, strict signatures) affect behaviour and performance. All commands are reproducible with fixed seeds.

## Experiment 1: Trust skeleton and dual approval

**Command:**

```bash
labtrust reproduce --profile minimal
```

Use `--profile full` for more episodes per condition. Custom output: `--out runs/my_repro`.

**What it varies:** `trust_skeleton` [on, off] × `dual_approval` [on, off] → 4 conditions per task. See [Reproduce](../benchmarks/reproduce.md).

**What to compare:** Throughput and violations across conditions. Figures and data tables are under:

- `runs/repro_minimal_<timestamp>/taska/figures/` and `taska/figures/data_tables/`
- `runs/repro_minimal_<timestamp>/taskc/figures/` and `taskc/figures/data_tables/`

Examples: `throughput_vs_violations.png`, `trust_cost_vs_p95_tat.png`, `violations_by_invariant_id.png`, `blocked_by_reason_code_top10.png`.

**What it illustrates:** With the trust skeleton on and dual approval where required, the engine enforces invariants and blocks unsafe actions (BLOCKED + reason codes). With trust off, violations can increase. The trade-off: trust adds control and auditability at the cost of extra checks.

**Output location:** `runs/repro_minimal_<timestamp>/` (or the path given by `--out`).

---

## Experiment 2: Strict signatures and containment (insider_key_misuse)

**Command:**

```bash
labtrust package-release --profile paper_v0.1 --seed-base 100 --out release_paper
```

To run only the insider study (no full release):

```bash
labtrust run-study --spec policy/studies/study_spec.taskf_insider.v0.1.yaml --out <dir>
```

**What it varies:** `strict_signatures` [false, true] across insider attack phases: RBAC deny, forged signature, replay, token misuse.

**What to compare:** In the study results:

- `fraction_of_attacks_contained`
- `time_to_first_detected_security_violation`
- `forensic_quality_score`

See [Benchmarks](../benchmarks/benchmarks.md) (insider_key_misuse) for metric definitions.

**What it illustrates:** With `strict_signatures: true`, forged and replayed signatures are BLOCKED (SIG_INVALID). With `strict_signatures: false`, the simulator may accept them. Containment and forensic quality are only achieved when the trust mechanism (signatures) is enabled.

**Output location:** Paper profile: `<dir>/_study/`, `TABLES/`, `FIGURES/`. Study-only: `<dir>/results/cond_*/`, `figures/`.

---

## Experiment 3 (optional): Quick baseline

**Command:**

```bash
labtrust quick-eval --seed 42
```

**What it does:** One episode each of throughput_sla, adversarial_disruption, and multi_site_stat with scripted baselines.

**What it illustrates:** Baseline performance and metrics (throughput, violations, blocked counts) with the default trust skeleton; useful as a reference before running reproduce or paper experiments.

---

## Reproducibility

- **Seeding and determinism:** Same seed + same code + same policy ⇒ same results. See [Reproduce](../benchmarks/reproduce.md) for seeding and study manifests.
- **Paper profile and study specs:** See [Paper provenance](../benchmarks/paper/README.md) for the paper_v0.1 profile and figure/table provenance.
