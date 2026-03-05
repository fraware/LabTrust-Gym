# Forker guide: get started and extend for your organization

This guide is for organizations that fork LabTrust-Gym to run coordination benchmarks, security and safety suites, and determine the best coordination technique at scale. It covers (1) getting started: clone, customize policy, run everything; and (2) pipeline and extension: out-of-the-box flow, partner overlays, and how to extend.

**One-command quickstart:** From a clean clone, run `labtrust forker-quickstart --out <dir>` (or `bash scripts/forker_quickstart.sh [<dir>]` / `scripts/forker_quickstart.ps1` on Windows). This runs validate-policy, coordination security pack, build-lab-coordination-report, and export-risk-register. See [Troubleshooting](troubleshooting.md) if something fails. For a table of canonical demo commands and minimal end-to-end stories, see [Quick demos](quick_demos.md).

**How-to guides:** [Add a coordination method](../operations/howto_add_coordination_method.md), [add a risk injection](../operations/howto_add_injection.md), [tune the selection policy](../operations/howto_selection_policy.md), [interpret security/gate failures](../operations/howto_security_gate_failures.md).

---

## Part 1 — Getting started

### 1.1 Prerequisites

- **Python 3.11+** (3.12 recommended).
- **Git** (fork on GitHub/GitLab, then clone your fork).
- **Windows:** Use PowerShell for the scripts below. Avoid repo paths with accented characters; clone to a path like `C:\LabTrust-Gym` if needed. See [Installation](installation.md).

### 1.2 Clone and install

```bash
git clone https://github.com/YOUR_ORG/LabTrust-Gym.git
cd LabTrust-Gym
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev,env,plots]"
labtrust --version
```

Policy is read from the repo `policy/` when developing from source. Override with `LABTRUST_POLICY_DIR` if needed.

### 1.3 What to customize (policy-only)

All of the following are data-driven under `policy/`. No engine code change is required for typical lab customization.

| What | Where |
|------|--------|
| Partner overlay | `policy/partners/<partner_id>/`; register in `policy/partners/partners_index.v0.1.yaml` |
| Zones and layout | `policy/zones/zone_layout_policy.v0.1.yaml` |
| Catalogue | `policy/catalogue/` |
| Coordination methods | `policy/coordination/coordination_methods.v0.1.yaml` |
| Scale configs | `policy/coordination/scale_configs.v0.1.yaml` |
| Coordination study spec | `policy/coordination/coordination_study_spec.v0.1.yaml` |
| Selection policy | `policy/coordination/coordination_selection_policy.v0.1.yaml` |
| Risk registry | `policy/risks/risk_registry.v0.1.yaml` |
| RBAC | `policy/rbac/rbac_policy.v0.1.yaml` |
| Reason codes | `policy/reason_codes/reason_code_registry.v0.1.yaml` |
| Invariants | `policy/invariants/` |
| Golden scenarios | `policy/golden/golden_scenarios.v0.1.yaml` |

**Partner overlay (recommended):** Add an entry in `policy/partners/partners_index.v0.1.yaml`, create `policy/partners/<partner_id>/` with overrides (e.g. copy from `policy/partners/hsl_like/`), then run `labtrust validate-policy --partner <partner_id>` and use `--partner <partner_id>` on benchmark and forker commands.

**Path B (no fork):** Depend on `labtrust-gym` as a library and ship your own pip-installable package; use [Extension development](../agents/extension_development.md) and [Lab profile reference](../reference/lab_profile_reference.md).

### 1.4 Validate and test

```bash
labtrust validate-policy
# With partner: labtrust validate-policy --partner hsl_like
pytest -q
# Or: make test
```

**Forker quickstart (recommended after customizing policy):**

```bash
labtrust forker-quickstart --out labtrust_runs/forker_quickstart
```

### 1.5 Commands summary

Outputs go to `labtrust_runs/` or `--out`. Key commands: `validate-policy`, `quick-eval`, `bench-smoke`, `run-benchmark`, `eval-agent`, `export-receipts`, `export-fhir`, `verify-bundle`, `verify-release`, `run-security-suite`, `safety-case`, `export-risk-register`, `run-coordination-security-pack`, `build-lab-coordination-report`, `run-coordination-study`, `summarize-coordination`, `run-study`, `make-plots`, `reproduce`, `package-release`, `run-official-pack`. See the main [index](../index.md) CLI table for full list.

### 1.6 End-to-end demo stories (<15 min)

Two minimal sequences you can run from a clean clone to reproduce a full pipeline in under 15 minutes.

**Story 1 (default policy)**

Run from repo root:

1. `labtrust validate-policy`
2. `labtrust quick-eval --seed 42 --out-dir labtrust_runs/demo`
3. `labtrust run-coordination-security-pack --out labtrust_runs/demo/pack --matrix-preset hospital_lab`
4. `labtrust export-risk-register --out labtrust_runs/demo/risk_out --runs labtrust_runs/demo/pack`

**Expected outputs:** Exit 0 at each step. You should see: `labtrust_runs/demo/quick_eval_*/summary.md`; `labtrust_runs/demo/pack/pack_summary.csv` and `pack_gate.md`; `labtrust_runs/demo/pack/summary/sota_leaderboard.md`, `sota_leaderboard_full.md`, `method_class_comparison.md` (when the pack is summarized); `labtrust_runs/demo/risk_out/RISK_REGISTER_BUNDLE.v0.1.json`. Optional: if a run produced receipts, run `labtrust verify-bundle --bundle <path>` on one EvidenceBundle under `receipts/.../EvidenceBundle.v0.1`.

**Story 2 (HSL-like partner)**

Same flow with `--partner hsl_like` on every command: `validate-policy --partner hsl_like`, `quick-eval --seed 42 --out-dir labtrust_runs/demo --partner hsl_like`, `run-coordination-security-pack --out labtrust_runs/demo/pack --matrix-preset hospital_lab --partner hsl_like`, `export-risk-register --out labtrust_runs/demo/risk_out --runs labtrust_runs/demo/pack`. The only difference is that the partner overlay is used; outputs have the same structure, with `partner_id` present in the bundle where applicable.

### 1.7 Demo scenarios by partner

Treat each partner as a concrete lab instance; run the same pipeline with `--partner <id>`.

| Partner | Commands to run | Tasks/scales | Success looks like |
|---------|-----------------|--------------|--------------------|
| **hsl_like** | `labtrust validate-policy --partner hsl_like`; `labtrust quick-eval --partner hsl_like --seed 42 --out-dir <dir>`; `labtrust run-coordination-security-pack --out <pack_dir> --matrix-preset hospital_lab --partner hsl_like`; `labtrust export-risk-register --out <risk_dir> --runs <pack_dir>` | Default from pack (hospital_lab) | (a) **verify-release passes** when run on the produced release (e.g. after building a release from that dir or running package-release and pointing to it). (b) **Gate verdicts** visible in `pack_gate.md`: PASS / FAIL / not_supported as expected per cell. |

### 1.8 Forker journey (case study)

A partner lab cloned the repo, added the HSL-like partner overlay (already present in the repo), and ran the forker path to produce benchmarks and a risk register. Outcome: benchmarks ran, the coordination pack produced `pack_gate.md` with verdicts per cell, and the risk register bundle was generated and validated.

**Commands (synthetic journey):**

1. Clone and install: `git clone ...`, `pip install -e ".[dev,env,plots]"`, `labtrust --version`
2. `labtrust validate-policy --partner hsl_like`
3. `labtrust forker-quickstart --out labtrust_runs/forker_quickstart`
4. `labtrust run-official-pack --out labtrust_runs/official_pack --seed-base 100 --include-coordination-pack`
5. `labtrust export-risk-register --out labtrust_runs/risk_out --runs labtrust_runs/official_pack`

Result: one output tree with baselines, SECURITY/, coordination pack outputs, and `RISK_REGISTER_BUNDLE.v0.1.json` suitable for audit or further verification.

### 1.9 Troubleshooting

See [Troubleshooting](troubleshooting.md) and [Installation](installation.md#troubleshooting).

---

## Part 2 — Pipeline and extension

### 2.1 Out-of-the-box pipeline (six steps)

Replace `<dir>`, `<dir2>`, `<dir3>` with actual paths.

1. **Validate policy:** `labtrust validate-policy` (or `--partner hsl_like`).
2. **Run coordination security pack:** `labtrust run-coordination-security-pack --out <dir> --matrix-preset hospital_lab`.
3. **Build lab coordination report:** `labtrust build-lab-coordination-report --pack-dir <dir> [--out <dir>]`.
4. **Use the decision:** Open `COORDINATION_DECISION.v0.1.json` or `COORDINATION_DECISION.md` for chosen method per scale; `LAB_COORDINATION_REPORT.md` for the full story.
5. **Export risk register:** `labtrust export-risk-register --out <dir2> --runs <dir>`.
6. **Optional (official pack):** `labtrust run-official-pack --out <dir3> --seed-base 42` then `labtrust export-risk-register --out <dir2> --runs <dir3>` (or `--include-official-pack <dir3>`).

### 2.2 Partner overlay (Path A)

1. Edit `policy/partners/partners_index.v0.1.yaml`: add `partner_id`, `description`, `overlay_path: "policy/partners/<partner_id>"`.
2. Create `policy/partners/<partner_id>/` with overlay files (see `hsl_like/`).
3. Validate: `labtrust validate-policy --partner <partner_id>`.
4. Use `--partner <partner_id>` on `run-benchmark`, `validate-policy`, `quick-eval`, `reproduce`, `run-coordination-security-pack`, `build-lab-coordination-report`, `run-coordination-study`, `run-official-pack`, `export-risk-register`.

Partner overlays can also provide risk registry, security attack suite, benchmark pack, and coordination study spec when those files exist under the partner path.

### 2.3 Coordination methods and scales

- **Methods:** `policy/coordination/coordination_methods.v0.1.yaml`. Forkers can add or tune methods within the schema.
- **Scale configs:** `policy/coordination/scale_configs.v0.1.yaml` (e.g. `small_smoke`, `medium_stress_signed_bus`, `corridor_heavy`).
- **Study matrix:** `policy/coordination/coordination_study_spec.v0.1.yaml`.
- **Best method at scale:** Decided by `recommend-coordination-method` using `policy/coordination/coordination_selection_policy.v0.1.yaml` (objective, constraints, per-scale rules).

### 2.4 Security and safety gates

<span id="security-and-safety-gates"></span>

The coordination security pack produces **pack_gate.md** (PASS/FAIL/not_supported per cell). Gate rules: `policy/coordination/coordination_security_pack_gate.v0.1.yaml`.

- **When the gate fails:** Any cell FAIL sets the coordination decision verdict to **security_gate_failed**. Resolve before deploying.
- **Check before release:** `labtrust check-security-gate --run <dir>` (exit 0 if all PASS or not_supported).

### 2.5 Interpreting outputs

- **COORDINATION_DECISION.v0.1.json** / **COORDINATION_DECISION.md**: Chosen method per scale (or "no admissible method" / "security_gate_failed").
- **LAB_COORDINATION_REPORT.md**: Stakeholder report (gate, risk matrix, leaderboard, decision, next steps).
- **pack_gate.md**: Pass/fail per cell.
- **SECURITY/coordination_risk_matrix.csv** (and .md): Method x injection outcomes.

### 2.6 Coordination selection policy

<span id="coordination-selection-policy"></span>

`policy/coordination/coordination_selection_policy.v0.1.yaml`: **objective** (e.g. maximize_overall_score), **constraints** (violations, attack success rate, cost ceiling), **per_scale_rules**. Copy and edit for your risk appetite.

### 2.7 Paths for extending

- **Path A (policy + partner only):** Same engine and tasks; add partner overlay, scale configs, coordination methods, or injections.
- **Path B (policy + custom tasks):** Fork and add a new task in `src/labtrust_gym/benchmarks/tasks.py` (subclass `BenchmarkTask`, register in `_TASK_REGISTRY`).

### 2.8 Verifying a release

- **Full release dir:** `labtrust verify-release --release-dir <dir> [--strict-fingerprints]`.
- **Single EvidenceBundle:** `labtrust verify-bundle --bundle <path>` (path under `receipts/.../EvidenceBundle.v0.1`).
- **E2E:** `bash scripts/ci_e2e_artifacts_chain.sh` (package-release minimal, export-risk-register, build-release-manifest, verify-release --strict-fingerprints).

### 2.9 Risk register and run layout

`export-risk-register` builds the bundle from policy and run dirs passed with `--runs`. Run dirs should contain e.g. `pack_summary.csv`, `SECURITY/`, `summary/`, `COORDINATION_DECISION.v0.1.json`. See [Risk register](../risk-and-security/risk_register.md).

---

## Related docs

- [Troubleshooting](troubleshooting.md)
- [Lab coordination report](../coordination/lab_coordination_report.md)
- [Coordination studies](../coordination/coordination_studies.md)
- [Security attack suite](../risk-and-security/security_attack_suite.md)
- [Risk register](../risk-and-security/risk_register.md)
