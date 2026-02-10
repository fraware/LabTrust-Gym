# Forker guide: run the pipeline and extend for your organization

This guide is for organizations that fork LabTrust-Gym to run coordination benchmarks, security and safety suites, and determine the best coordination technique at scale. The hospital lab (and HSL-like partner) remain the reference core; forkers extend or overlay policy and optionally add tasks.

**One-command quickstart:** From a clean clone, run `labtrust forker-quickstart --out <dir>` (or `bash scripts/forker_quickstart.sh [<dir>]` / `scripts/forker_quickstart.ps1` on Windows). This runs validate-policy, coordination security pack (fixed methods + critical injections), build-lab-coordination-report, and export-risk-register, then prints where to find COORDINATION_DECISION and the risk register. See [README](../README.md) and [Troubleshooting](troubleshooting.md) if something fails.

**How-to guides:** [Add a coordination method](howto_add_coordination_method.md), [add a risk injection](howto_add_injection.md), [tune the selection policy](howto_selection_policy.md), [interpret security/gate failures](howto_security_gate_failures.md).

---

## Out-of-the-box pipeline (copy-paste)

From a clean clone, this six-step sequence runs the full flow with default hospital lab policy. Replace `<dir>`, `<dir2>`, `<dir3>` with actual paths (e.g. `./labtrust_runs/pack`, `./risk_out`, `./official_out`).

1. **Validate policy**
   ```bash
   labtrust validate-policy
   ```
   With the default partner overlay: `labtrust validate-policy --partner hsl_like`

2. **Run coordination security pack**
   ```bash
   labtrust run-coordination-security-pack --out <dir> --matrix-preset hospital_lab
   ```
   This writes `pack_summary.csv`, `pack_gate.md`, and `SECURITY/coordination_risk_matrix.*` under `<dir>`.

3. **Build lab coordination report**
   ```bash
   labtrust build-lab-coordination-report --pack-dir <dir> [--out <dir>]
   ```
   If `--out` is omitted, artifacts are written into the pack directory. You get `COORDINATION_DECISION.v0.1.json`, `COORDINATION_DECISION.md`, and `LAB_COORDINATION_REPORT.md`.

4. **Use the decision**  
   Open `COORDINATION_DECISION.v0.1.json` or `COORDINATION_DECISION.md` for the **chosen method per scale**. Use `LAB_COORDINATION_REPORT.md` for the full story (gate, risk matrix, leaderboard, next steps).

5. **Export risk register**
   ```bash
   labtrust export-risk-register --out <dir2> --runs <dir>
   ```
   The bundle is written to `<dir2>/RISK_REGISTER_BUNDLE.v0.1.json`.

6. **Optional: official pack and risk register**
   ```bash
   labtrust run-official-pack --out <dir3> --seed-base 42
   labtrust export-risk-register --out <dir2> --runs <dir3>
   ```
   Or add to an existing export: `--runs <dir> --include-official-pack <dir3>`.

The same sequence works if you add a new partner overlay and pass `--partner <your_partner_id>` on commands that support it (see below), provided your policy validates and uses coordination method IDs and scale IDs referenced in the pack or study spec.

---

## Add a partner overlay (Path A)

Partner overlays let you override policy (critical thresholds, stability, enforcement) without changing engine code.

1. **Register the partner**  
   Edit `policy/partners/partners_index.v0.1.yaml`: add an entry with `partner_id`, `description`, and `overlay_path: "policy/partners/<partner_id>"`.

2. **Create the overlay directory**  
   Create `policy/partners/<partner_id>/` and add overlay files (same structure and schemas as base policy). Example: `policy/partners/hsl_like/` contains `calibration.v0.1.yaml`, `critical/critical_thresholds.v0.1.yaml`, `enforcement/enforcement_map.v0.1.yaml`, `stability/stability_policy.v0.1.yaml`. Only include files you override.

3. **Validate with partner**
   ```bash
   labtrust validate-policy --partner <partner_id>
   ```

4. **Use partner in runs**  
   Commands that accept `--partner` include `run-benchmark`, `validate-policy`, `quick-eval`, `reproduce`, `run-coordination-security-pack`, `build-lab-coordination-report`, `run-coordination-study`, `run-official-pack`, and `export-risk-register`. When set, the pipeline loads policy (and optionally risk registry, security suite, benchmark pack, or study spec) from `policy/partners/<partner_id>/` when overlay files exist; otherwise it falls back to base policy. Example:
   ```bash
   labtrust run-benchmark --task throughput_sla --episodes 5 --partner <partner_id> --out results.json
   ```

5. **Partner overlay for risk register and security suite**  
   With `--partner <id>`, `export-risk-register` loads the risk registry from `policy/partners/<id>/risks/risk_registry.v0.1.yaml` and the security attack suite from `policy/partners/<id>/golden/security_attack_suite.v0.1.yaml` when those files exist. Evidence entries in the bundle include `partner_id` for attribution so an org’s report can filter or label evidence by partner.

6. **Partner-scoped benchmark pack and study spec**  
   With `--partner <id>`, `run-official-pack` loads the benchmark pack from `policy/partners/<id>/official/benchmark_pack.v0.1.yaml` when present. For `run-coordination-study`, when `--partner <id>` is set, the spec is resolved from `policy/partners/<id>/coordination/coordination_study_spec.v0.1.yaml` when that file exists (overriding the path given by `--spec`).

---

## Coordination methods and scales

- **Methods** are defined in `policy/coordination/coordination_methods.v0.1.yaml`. Each entry has `method_id`, coordination class, and optional config. Forkers can add or tune methods within the schema; the benchmark and study runners are method-agnostic.

- **Scale configs** are in `policy/coordination/scale_configs.v0.1.yaml` (e.g. `small_smoke`, `medium_stress_signed_bus`, `corridor_heavy`). Studies and the pack use these IDs; you can add new scale configs for your workloads.

- **Study matrix** (scales, methods, injections) is defined in `policy/coordination/coordination_study_spec.v0.1.yaml`. Use it for `run-coordination-study`; the security pack uses its own matrix (fixed or from policy).

- **Best method at scale** is decided by `recommend-coordination-method`, which reads `policy/coordination/coordination_selection_policy.v0.1.yaml`. That file defines the objective (e.g. maximize_overall_score), hard constraints (violation rate, attack success rate, cost ceiling), and per-scale rules. Forkers can copy and edit this file to set their own constraints and objective; see [Coordination selection policy](#coordination-selection-policy) below.

---

## Security and safety gates

The coordination security pack produces **pack_gate.md** with a verdict (PASS / FAIL / not_supported) per cell (scale x method x injection). Gate rules are defined in `policy/coordination/coordination_security_pack_gate.v0.1.yaml` (e.g. attack_success_rate_zero, violations_within_delta, detection_within_steps).

- **When the gate fails:** If any cell has verdict **FAIL**, the coordination decision verdict is set to **security_gate_failed**. The decision artifact will list failed cells and recommend resolving them before deploying. Do not treat a run as admissible until the gate passes.

- **Check the gate before merging or releasing:** Run `labtrust check-security-gate --run <dir>` where `<dir>` is the output of `run-coordination-security-pack`. It exits 0 if all cells are PASS or not_supported, and exits 1 if any cell is FAIL. Use this in CI or release checklists to block on gate failure.

- **SECURITY_REPORT.md and SAFETY_CASE_REPORT.md:** When you run `build-lab-coordination-report`, the builder also writes **SECURITY_REPORT.md** (pack and gate summary, links to pack_gate and SECURITY/) and **SAFETY_CASE_REPORT.md** (when SAFETY_CASE/ is present). These are linked from LAB_COORDINATION_REPORT.md and give stakeholders a single place to see what passed or failed and how it ties to the coordination decision and risk register.

---

## Interpreting outputs

- **COORDINATION_DECISION.v0.1.json** / **COORDINATION_DECISION.md**: Chosen coordination method per scale (or "no admissible method", or "security_gate_failed" if the pack gate had any FAIL cell). Use this to decide which method to run in production for each scale.

- **LAB_COORDINATION_REPORT.md**: Stakeholder-facing report that ties together the pack gate, risk matrix, SOTA leaderboard, method-class comparison, the decision, and next steps. Point reviewers and operators here.

- **pack_gate.md**: Pass/fail per cell (scale x method x injection) from the coordination security pack gate rules.

- **SECURITY/coordination_risk_matrix.csv** (and .md): Method x injection x phase outcomes (e.g. attack success rate, detection latency) for benchmarking and risk comparison.

---

## Coordination selection policy

The file `policy/coordination/coordination_selection_policy.v0.1.yaml` controls how "best method at scale" is chosen:

- **objective**: e.g. `maximize_overall_score` (resilience scoring); alternatives may be added later.
- **constraints**: A method is admissible only if all pass. Examples: baseline violations ≤ 10, worst-case attack success rate ≤ 0.2, cost ceiling (e.g. 100 USD). You can add or relax constraints.
- **per_scale_rules**: Overrides per scale (e.g. `medium_stress_signed_bus` for hospital lab at scale with higher resilience weight).

Forkers can copy this file and edit objective, thresholds, and per-scale rules to match their organization's risk appetite and priorities.

---

## Paths for extending the repo

- **Path A (policy + partner only):** Use the same engine and tasks; add a new partner overlay and optionally new scale configs, coordination methods, or injections. Run the same pipeline (pack, build-lab-report, export-risk-register). Best when your workflow is lab-like (resources, queues, zones, devices).

- **Path B (policy + custom tasks):** Fork and add a new task. Tasks are registered in `src/labtrust_gym/benchmarks/tasks.py`: subclass `BenchmarkTask`, implement the required interface (initial_state, episode length, etc.), and add an entry to `_TASK_REGISTRY`. Then use the new task id in `run-benchmark` and in study specs. The coordination and security pipeline (same action set and runner output contract) stays unchanged.

- **Path C (future):** Future work may introduce a domain adapter layer that maps abstract workflows to the current engine action set so multiple sectors share the same coordination/benchmark/security pipeline; hospital lab would remain the reference implementation.

---

## Verifying a release

To verify a **full release directory** (output of `package-release`), use `labtrust verify-release --release-dir <dir>`. This discovers every `EvidenceBundle.v0.1` under `receipts/`, runs the same checks as verify-bundle on each, and exits non-zero if any fail. You can also run the E2E script (`bash scripts/ci_e2e_artifacts_chain.sh`), which runs package-release minimal, verify-release, and export-risk-register. To verify a **single** EvidenceBundle (e.g. one receipt dir), use `labtrust verify-bundle --bundle <path to EvidenceBundle.v0.1>`. The `--bundle` argument must point at a directory that contains `manifest.json` (i.e. a path under `receipts/.../EvidenceBundle.v0.1`), not the release root.

## Risk register and run directory layout

`export-risk-register` builds the bundle from policy and from run directories you pass with `--runs`. It expects run dirs to contain the usual layout: e.g. `pack_summary.csv`, `SECURITY/`, `summary/`, `COORDINATION_DECISION.v0.1.json`, `LAB_COORDINATION_REPORT.md`, etc. So you can run your own pack or coordination study and pass that directory to `--runs`; the bundle will list present evidence and stub missing evidence. See [Risk register](risk_register.md) for details.

---

## Related docs

- [Troubleshooting](troubleshooting.md) – verify-bundle (manifest.json missing), policy validation, pack gate failures, E2E chain.
- [How-to: add coordination method](howto_add_coordination_method.md), [add injection](howto_add_injection.md), [selection policy](howto_selection_policy.md), [security/gate failures](howto_security_gate_failures.md).
- [Modular fork roadmap](MODULAR_FORK_ROADMAP.md) – design balance (platform vs hospital lab core).
- [Pipeline overview](pipeline_overview.md) – capabilities and end-to-end flows.
- [Lab coordination report](lab_coordination_report.md) – canonical hospital lab flow.
- [Coordination studies](coordination_studies.md) – study runner, summary, Pareto.
- [Security attack suite](security_attack_suite.md) – coordination security pack, gate rules.
- [Risk register](risk_register.md) – bundle generation and coverage.
