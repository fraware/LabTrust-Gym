# Paper-ready release profile

The **paper_v0.1** profile produces a self-contained, offline-ready artifact suitable for review and reproduction. It is benchmark-first: official baselines, one study (insider_key_misuse strict_signatures ablation), summarized results, receipts with verification, and canonical figures/tables.

## Exact commands for reviewers

From the repository root, with a fixed seed for full determinism:

```bash
labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>
```

Example (artifact in `release_paper/`):

```bash
labtrust package-release --profile paper_v0.1 --seed-base 100 --out release_paper
```

- **Offline**: No network required; all inputs are under `policy/` and the codebase.
- **Determinism**: With `--seed-base 100`, timestamps in `metadata.json` and baseline metadata are deterministic (UTC epoch + seed-base seconds).
- **Output**: A single directory containing everything below.

## Official tasks and claimed metrics

Which tasks and baselines are official, which metrics are claimed, and where the numbers come from (file paths).

| Task | Description | Official baseline |
|------|-------------|-------------------|
| throughput_sla | Throughput under SLA | scripted_ops_v1 |
| stat_insertion | STAT insertion under load | scripted_ops_v1 |
| qc_cascade | QC fail cascade | scripted_ops_v1 |
| adversarial_disruption | Adversarial disruption | adversary_v1 |
| multi_site_stat | Multi-site STAT | scripted_ops_v1 |
| insider_key_misuse | Insider and key misuse | insider_v1 |

Registry: `benchmarks/baseline_registry.v0.1.yaml`. Regenerate with `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force`.

| Metric | File path (in release artifact) |
|--------|---------------------------------|
| Throughput (mean/std) | summary_v0.2.csv (throughput_mean, throughput_std) |
| p95 TAT | summary_v0.2.csv (p95_turnaround_s_mean, p95_turnaround_s_std) |
| Violations | results/*.json episodes[].metrics.violations_by_invariant_id |
| Official baseline table | benchmarks/baselines_official/v0.2/summary_v0.2.csv |

**Reproducing from a release tarball:** (1) pip install labtrust-gym[env,plots]; (2) labtrust validate-policy; (3) labtrust quick-eval --seed 42; (4) labtrust package-release --profile paper_v0.1 --seed-base 100 --out dir; (5) labtrust verify-bundle --bundle `dir/receipts/.../EvidenceBundle.v0.1` (or use `labtrust verify-release --release-dir dir`). See [Frozen contracts](frozen_contracts.md) and [Reproduce](reproduce.md). Optional: Zenodo DOI for v0.1.0; add doi to CITATION.cff.

## What the profile runs

1. **Official baselines** into `<dir>/_baselines/`  
   - Tasks A–F, 50 episodes each, seed = seed-base.  
   - Writes `results/*.json`, `summary.csv`, `summary.md`, `metadata.json`.

2. **insider_key_misuse strict_signatures study** into `<dir>/_study/`  
   - Ablations: `strict_signatures: [false, true]`, 50 episodes per condition.  
   - Writes `manifest.json`, `results/cond_*/results.json`, `logs/cond_*/episodes.jsonl`, `figures/`.

3. **Summarize** across official + study  
   - Combined aggregation → `<dir>/TABLES/summary.csv`, `summary.md`, `paper_table.md`.

4. **Representative run per task**  
   - One episode per task (A–F) with episode log; export receipts; verify bundle.  
   - Receipts and verification reports under `<dir>/receipts/<task>/`.

4b. **Security attack suite and securitization packet**  
   - Run security suite (smoke-only, seed = seed-base); write `<dir>/SECURITY/attack_results.json`.  
   - Emit securitization packet: `SECURITY/coverage.json`, `coverage.md`, `reason_codes.md`, `deps_inventory.json`.  
   - See [Security attack suite](security_attack_suite.md).

4c. **Safety case**  
   - Emit safety case from `policy/safety_case/claims.v0.1.yaml`: `<dir>/SAFETY_CASE/safety_case.json`, `<dir>/SAFETY_CASE/safety_case.md` (claim to control, test, artifact, verification command).  
   - See [Implementation verification](implementation_verification.md).

5. **FIGURES/**  
   - 2–3 canonical plots from the insider_key_misuse study (e.g. throughput vs violations, trust cost vs p95 TAT).

6. **RELEASE_NOTES.md**  
   - What ran, versions (git SHA, seed-base), deterministic timestamp note.

7. **metadata.json**, **BENCHMARK_CARD.md**, **MANIFEST.v0.1.json**  
   - For artifact integrity and citation.

8. **COORDINATION_CARD.md**, **COORDINATION_LLM_CARD.md**, and **_coordination_policy/**  
   - Coordination benchmark card (policy fingerprint, scenario generation, methods, injections, metrics, determinism, limitations); LLM coordination card (LLM methods, backends, injection coverage, known limitations); frozen copy of coordination policy files with `manifest.json` for auditable reproduction. See [Coordination benchmark card](coordination_benchmark_card.md) and [LLM Coordination Protocol](llm_coordination_protocol.md).

9. **Optional: coordination pack and lab report**  
   - With `--include-coordination-pack`, the profile also runs the coordination security pack into `<dir>/_coordination_pack/` (pack_summary.csv, pack_gate.md, SECURITY/coordination_risk_matrix.*) and builds the lab report (LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.v0.1.json). COORDINATION_MATRIX/ is then populated from the pack. See [Lab coordination report](lab_coordination_report.md).

## Artifact layout (after run)

```
<dir>/
  RELEASE_NOTES.md
  metadata.json
  BENCHMARK_CARD.md
  MANIFEST.v0.1.json
  COORDINATION_CARD.md
  COORDINATION_LLM_CARD.md
  _coordination_policy/
  SAFETY_CASE/
    safety_case.json
    safety_case.md
    (frozen policy YAMLs + manifest.json)
  _baselines/
    results/
      throughput_sla_scripted_ops.json
      stat_insertion_scripted_ops.json
      ...
    summary.csv
    summary.md
    metadata.json
  _study/
    study_spec_taskf_strict_signatures.yaml
    manifest.json
    results/
      cond_0/results.json
      cond_1/results.json
    logs/
      cond_0/episodes.jsonl
      cond_1/episodes.jsonl
    figures/
      *.png, *.svg
  FIGURES/
    (copies of _study/figures/)
  TABLES/
    summary.csv
    summary.md
    paper_table.md
  receipts/
    throughput_sla/
      EvidenceBundle.v0.1/
      verify_report.txt
    stat_insertion/
    ...
  SECURITY/
    attack_results.json
    coverage.json
    coverage.md
    reason_codes.md
    deps_inventory.json
  _repr/
    throughput_sla/
      episodes.jsonl
      results.json
    ...
```

## Smoke test (few episodes)

For a quick check (e.g. in CI), set `LABTRUST_PAPER_SMOKE=1` so the profile uses 1 episode for baselines and 2 for the insider_key_misuse study:

```bash
LABTRUST_PAPER_SMOKE=1 labtrust package-release --profile paper_v0.1 --seed-base 100 --out release_paper_smoke
```

## Reproducing with the same seed

To reproduce the same artifact (including deterministic timestamps):

```bash
labtrust package-release --profile paper_v0.1 --seed-base 100 --out release_paper
```

Same `--seed-base` and codebase ⇒ same baseline metrics, study results, and metadata timestamps.

## Optional: include coordination pack and lab report

To include the coordination security pack and lab report in the artifact (so the release contains pack_summary.csv, LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.* in `_coordination_pack/` and a real coordination matrix from pack mode):

```bash
labtrust package-release --profile paper_v0.1 --seed-base 100 --out release_paper --include-coordination-pack
```

See [Lab coordination report](lab_coordination_report.md) for the report format and how to run the pack and report separately.

## Optional: keep intermediate dirs

The command does not delete `_baselines`, `_study`, or `_repr`; they remain for inspection. To regenerate from scratch, use a new `--out` directory or remove the existing one first.
