# Trust ablation study pack

The **trust ablations** study (`policy/studies/trust_ablations.v0.1.yaml`) is a standard multi-dimension sweep for paper-ready plots. It expands a Cartesian product of trust-related knobs, runs the benchmark per condition with deterministic seeds, and produces Pareto scatter plots plus a summary table (used in `docs/paper_ready.md`).

## Running the study

```bash
labtrust run-study --spec policy/studies/trust_ablations.v0.1.yaml --out runs/trust_ablations
labtrust make-plots runs/trust_ablations
```

Output: `runs/trust_ablations/manifest.json`, `conditions.jsonl`, `results/<cond_id>/results.json`, `logs/<cond_id>/episodes.jsonl`, `figures/*.png`, `figures/data_tables/summary.csv`, `figures/data_tables/paper_table.md`.

## Ablation knobs and expected effects

Each knob is a dimension in the sweep. The runner allocates one **deterministic seed** per condition: `seed_base + condition_index` (same spec ⇒ same seed per condition).

### `trust_skeleton` (on | off)

- **Meaning**: Enable or disable the full trust skeleton (hashchain, tokens, RBAC enforcement, forensic freeze).
- **Expected effect**:
  - **on**: Fewer invariant violations and blocked actions that would break policy; possible extra latency and coordination overhead (token minting/consumption, dual approval).
  - **off**: Higher throughput if the policy is not stressed; more risk of violations and unreported nonconformances. Useful as a baseline to measure “cost of trust”.

### `rbac` (coarse | fine)

- **Meaning**: Role-based access control granularity. Coarse = fewer roles / broader allowed actions; fine = more roles and tighter action sets per role.
- **Expected effect**:
  - **coarse**: Fewer RBAC denials; simpler policy; less isolation between roles.
  - **fine**: More precise least-privilege; can reduce certain failure modes (e.g. wrong role performing critical action) but may increase blocked actions and coordination.

### `dual_approval` (on | off)

- **Meaning**: Require dual approval (separation of duties) for selected critical actions (e.g. release, critical result ack).
- **Expected effect**:
  - **on**: Stronger audit trail and separation of duties; can reduce single-actor misuse. Typically adds latency and requires a second actor/token.
  - **off**: Lower latency and simpler flow; no dual-approval checks.

### `log_granularity` (minimal | full)

- **Meaning**: Audit log granularity: minimal = essential events only; full = detailed event payload and hashchain per step.
- **Expected effect**:
  - **minimal**: Smaller logs, faster writes; less forensic detail.
  - **full**: Full hashchain and event payloads for verification and receipts; slightly higher I/O and storage.

### Optional: `strict_signatures` (true | false)

- **Meaning**: When true, mutating actions require a valid signature (key_id + signature); when false, signature checks are advisory or skipped.
- **Expected effect**: Used in TaskF-style studies (LLM/insider). **true** ⇒ better containment of unsigned/misused actions; **false** ⇒ baseline with no signature enforcement.

## Condition labels

The spec can define **condition_labels**: one string per condition in the same order as the Cartesian product (sorted ablation keys). If omitted, the runner derives labels from the condition dict (e.g. `dual_approval_on_log_granularity_minimal_rbac_coarse_trust_skeleton_on`). Labels are written to `conditions.jsonl`, `manifest.json`, and used in Pareto scatter plots and `summary.csv` / `paper_table.md`.

## Smoke test

With **LABTRUST_REPRO_SMOKE=1**, the study runner caps episodes to **1** per condition so the trust ablations study runs a tiny version. Use this to assert artifact files exist without a long run:

```bash
LABTRUST_REPRO_SMOKE=1 labtrust run-study --spec policy/studies/trust_ablations.v0.1.yaml --out runs/trust_ablations_smoke
LABTRUST_REPRO_SMOKE=1 labtrust make-plots runs/trust_ablations_smoke
```

See `tests/test_trust_ablations_smoke.py` for the automated smoke test.
