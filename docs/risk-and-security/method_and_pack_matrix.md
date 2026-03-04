# Method and pack matrix view

Two matrix views support coordination methods and the security suite: **method x risk coverage** and **pack matrix (method x scale x injection)**. Both are policy-driven and can be rendered as markdown tables or exported to CSV for Excel. The pack matrix depends on **scale (number of agents)**, which is important for the pathology lab (blood sciences) taxonomy.

## 1. Method x risk coverage matrix

**Source:** `policy/coordination/method_risk_matrix.v0.1.yaml`

Each cell is a (method_id, risk_id) with:

- **coverage:** not_applicable | covered | partially_covered | uncovered
- **rationale:** short explanation
- **required_bench:** whether this cell must have evidence in the risk register (coverage gate)

This matrix defines which risks apply to which coordination methods and is used by the coverage gate (`labtrust validate-coverage --strict`) and by [Gate and required bench](gate_and_required_bench.md).

### View or export

```bash
# Terminal table (default)
labtrust show-method-risk-matrix

# Markdown (for docs or paste)
labtrust show-method-risk-matrix --format markdown

# CSV (open in Excel)
labtrust show-method-risk-matrix --format csv --out method_risk_matrix.csv
```

---

## 2. Pack matrix (method x scale x injection)

**Source:** `policy/coordination/coordination_security_pack.v0.1.yaml` (and optional `--matrix-preset`)

The coordination security pack runs a Cartesian product of **method_ids x scale_ids x injection_ids**. Each cell is one run (e.g. one episode) at that scale. The **scale** determines the **number of agents** (and sites, devices, etc.), so the matrix is explicitly scale-dependent.

### Scale taxonomy (number of agents)

The matrix depends on the number of agents collaborating in the blood sciences (pathology lab) run. Scale configs are defined in `policy/coordination/scale_configs.v0.1.yaml`. Typical presets:

| scale_id                 | num_agents_total | Use |
|--------------------------|------------------|-----|
| small_smoke              | 4                | Fast smoke / unit test |
| medium_stress_signed_bus | 75               | Pathology lab (blood sciences) at scale; signed bus and identity evaluation |
| corridor_heavy           | 200              | High contention routing stress |

Two presets use these scales: **hospital_lab** (4 methods; fast regression) and **hospital_lab_full** (all 30 coordination methods; full benchmark). Both use `small_smoke` and `medium_stress_signed_bus`, so you get 4-agent and 75-agent runs for each (method, injection) pair. This taxonomy is important when interpreting pack results: a method’s resilience or attack surface can differ by agent count.

### View or export

```bash
# Default pack (fixed methods/injections)
labtrust show-pack-matrix

# Pathology lab (blood sciences) preset (4 methods; fast)
labtrust show-pack-matrix --matrix-preset hospital_lab

# Full benchmark (all 30 coordination methods; same scales/injections)
labtrust show-pack-matrix --matrix-preset hospital_lab_full

# Markdown (includes scale taxonomy table)
labtrust show-pack-matrix --format markdown --matrix-preset hospital_lab

# CSV for Excel (includes num_agents_total per scale)
labtrust show-pack-matrix --format csv --matrix-preset hospital_lab --out pack_matrix.csv
```

---

## 3. Result matrix (real results from tests)

The **result matrix** is the same (method x scale x injection) grid filled with **real outcomes** from running the coordination security pack: metrics and verdicts (PASS / FAIL / SKIP / not_supported). No placeholders.

### Produce real results

Run the pack once; it runs all cells (deterministic, 1 episode per cell) and writes:

- `pack_summary.csv` – full metrics (throughput, violations, attack_success_rate, detection_latency_steps, etc.)
- `pack_gate.md` – verdict and rationale per cell
- `SECURITY/coordination_risk_matrix.csv` and `SECURITY/coordination_risk_matrix.md` – result matrix with verdicts

```bash
# Fast regression (4 methods x 2 scales x 4 injections = 32 cells)
labtrust run-coordination-security-pack --out labtrust_runs/pack_real --matrix-preset hospital_lab --seed 42

# Full benchmark (all 30 methods x 2 scales x 4 injections = 240 cells)
labtrust run-coordination-security-pack --out labtrust_runs/pack_full --matrix-preset hospital_lab_full --seed 42
```

You can also use `--methods-from full` (and optionally `--injections-from critical` or `policy`) instead of a preset. Output directory: the path you pass to `--out`.

### Run one scale at a time (shorter jobs)

To reduce runtime per run, you can run the full matrix one scale at a time with `--scale-ids`. Each scale writes to its own `--out` directory; combine them later with `export-risk-register --runs <dir1> --runs <dir2> --runs <dir3>`.

```bash
# Scale 1: small_smoke (4 agents, fastest)
labtrust run-coordination-security-pack --out pack_run_full_matrix/small_smoke --matrix-preset full_matrix --scale-ids small_smoke --seed 42 --workers 8

# Scale 2: medium_stress_signed_bus (75 agents)
labtrust run-coordination-security-pack --out pack_run_full_matrix/medium_stress_signed_bus --matrix-preset full_matrix --scale-ids medium_stress_signed_bus --seed 42 --workers 8

# Scale 3: corridor_heavy (200 agents)
labtrust run-coordination-security-pack --out pack_run_full_matrix/corridor_heavy --matrix-preset full_matrix --scale-ids corridor_heavy --seed 42 --workers 8
```

Scripts: `scripts/run_pack_by_scale.ps1` (Windows), `scripts/run_pack_by_scale.sh` (Unix/macOS).

### View the result matrix (real data)

Use the pack run directory as input:

```bash
# Markdown (full matrix with verdicts and security metrics)
labtrust show-pack-results --run labtrust_runs/pack_real

# Terminal table (method_id, scale_id, injection_id, verdict, attack_success_rate)
labtrust show-pack-results --run labtrust_runs/pack_real --format table

# CSV (same columns as SECURITY/coordination_risk_matrix.csv)
labtrust show-pack-results --run labtrust_runs/pack_real --format csv --out pack_results.csv
```

All data comes from the run; there are no placeholders. To refresh results, re-run the pack and point `--run` at the new directory.

---

## 4. Alignment with coordination methods and security suite

- **Method list:** Coordination methods are in `policy/coordination/coordination_methods.v0.1.yaml`. The method–risk matrix and pack config should list method_ids that exist there; add or extend cells when adding new methods or risks.
- **Injections:** Pack injection_ids come from `policy/coordination/injections.v0.2.yaml` (and the runtime injection registry). The security attack suite also includes broader IDs (e.g. SEC-PI-*, SEC-LLM-ATTACK-*) where relevant to coordination; see [Security attack suite](security_attack_suite.md).
- **Coverage:** Every (method_id, risk_id) with `required_bench: true` in the method–risk matrix must have evidence (or a waiver) when using `labtrust validate-coverage --strict`. Evidence is produced by running the coordination security pack or studies and then `labtrust export-risk-register --runs <dir>`.

---

## 5. Regenerating tables in this doc

The tables in this page can be regenerated from policy so they stay in sync:

```bash
labtrust show-method-risk-matrix --format markdown --out docs/risk-and-security/generated_method_risk_matrix.md
labtrust show-pack-matrix --format markdown --matrix-preset hospital_lab --out docs/risk-and-security/generated_pack_matrix.md
```

Then include or link the generated files if you want the site to show full tables. Otherwise, use the CLI or CSV export on demand.
