# Getting started: fork, customize, and run everything

This guide is for someone new to the repo who has forked it and wants to (1) customize policy and workflow for their hospital lab, and (2) run all supported commands and tests end-to-end. It assumes you are at the repo root after cloning your fork.

---

## 1. Prerequisites

- **Python 3.11+** (3.12 recommended).
- **Git** (fork on GitHub/GitLab, then clone your fork).
- **Windows:** Use PowerShell for the scripts below. Avoid repo paths with accented characters (e.g. in your username); clone to a path like `C:\LabTrust-Gym` if needed.
- **Optional:** Conda if you prefer a dedicated environment or need CPU-only PyTorch (e.g. AMD / no CUDA). See [Installation](installation.md#development-editable-install).

---

## 2. Clone and install

From your fork URL (replace with your own):

```bash
git clone https://github.com/YOUR_ORG/LabTrust-Gym.git
cd LabTrust-Gym
```

Create a virtual environment and install the package with dev, environment, and plotting extras:

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

pip install -e ".[dev,env,plots]"
```

Verify:

```bash
labtrust --version
```

If `labtrust` is not on PATH, use:

```bash
python -m labtrust_gym.cli.main --version
```

Policy is read from the repo `policy/` directory when developing from source. To override: `$env:LABTRUST_POLICY_DIR = "C:\path\to\policy"` (PowerShell) or `export LABTRUST_POLICY_DIR=/path/to/policy` (bash).

---

## 3. What to customize for your hospital lab

All of the following are **data-driven**: edit YAML/JSON under `policy/` (and optionally add a partner overlay). No engine code change is required for typical lab customization.

| What | Where | Purpose |
|------|--------|---------|
| **Partner overlay** | `policy/partners/<partner_id>/` | Your lab’s critical thresholds, enforcement, stability, calibration. Copy `policy/partners/hsl_like/` as a template. |
| **Partner index** | `policy/partners/partners_index.v0.1.yaml` | Register `partner_id` and `overlay_path`. |
| **Zones and layout** | `policy/zones/zone_layout_policy.v0.1.yaml` | Zone IDs, names, kinds, temperature bands, RBAC, connectivity. |
| **Catalogue** | `policy/catalogue/` | Test catalogue (e.g. assays, specimen types) for your lab. |
| **Coordination methods** | `policy/coordination/coordination_methods.v0.1.yaml` | Coordination techniques used in benchmarks and studies. |
| **Scale configs** | `policy/coordination/scale_configs.v0.1.yaml` | Scale definitions (e.g. small_smoke, medium_stress_signed_bus). |
| **Coordination study spec** | `policy/coordination/coordination_study_spec.v0.1.yaml` | Matrix of scales, methods, injections for `run-coordination-study`. |
| **Selection policy** | `policy/coordination/coordination_selection_policy.v0.1.yaml` | How “best method at scale” is chosen (constraints, objective). |
| **Risk registry** | `policy/risks/risk_registry.v0.1.yaml` | Risks and coverage for the risk register. |
| **RBAC** | `policy/rbac/rbac_policy.v0.1.yaml` | Roles and permissions. |
| **Reason codes** | `policy/reason_codes/reason_code_registry.v0.1.yaml` | Reason codes for audit and reporting. |
| **Invariants** | `policy/invariants/` | Invariant registries (tokens, zones, critical results). |
| **Golden scenarios** | `policy/golden/golden_scenarios.v0.1.yaml` | Scenarios used by the golden test suite. |

**Partner overlay (recommended path):**

1. Add an entry in `policy/partners/partners_index.v0.1.yaml` with `partner_id` and `overlay_path: "policy/partners/<partner_id>"`.
2. Create `policy/partners/<partner_id>/` and add only the files you override (e.g. `critical/critical_thresholds.v0.1.yaml`, `enforcement/enforcement_map.v0.1.yaml`, `stability/stability_policy.v0.1.yaml`, `calibration.v0.1.yaml`). See `policy/partners/hsl_like/` for structure.
3. Run `labtrust validate-policy --partner <partner_id>` and use `--partner <partner_id>` on benchmark and forker commands.

Details: [Forker guide](FORKER_GUIDE.md) (partner overlay, coordination methods, security gates, risk register).

---

## 4. Validate policy and run tests

Always validate policy after editing YAML/JSON:

```bash
labtrust validate-policy
```

With a partner:

```bash
labtrust validate-policy --partner hsl_like
```

**Fast test run** (excludes some env-heavy smoke tests):

```bash
pytest -q --ignore=tests/test_pz_parallel_smoke.py --ignore=tests/test_pz_aec_smoke.py --ignore=tests/test_benchmark_smoke.py
```

Or use the Makefile: `make test`.

**Full test suite** (all tests including PettingZoo and benchmark smoke):

```bash
pytest -v
```

Expect **1059 passed, 51 skipped** in about 10 minutes. Skips are intentional (optional MARL/golden/live-LLM backends or env). See [Testing strategy](testing_strategy.md).

**Golden suite** (with real engine): `make golden` or `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -v`.

**CLI smoke matrix** (exercises every CLI command with minimal args; can be slow, e.g. forker-quickstart ~6 min):

```bash
pytest tests/test_cli_smoke_matrix.py -v
```

---

## 5. Commands to run (in order)

Outputs go to `labtrust_runs/` or the path you pass with `--out` / `--out-dir`. Do not commit those outputs; they are gitignored.

### 5.1 Policy and validation

| Command | Description |
|---------|-------------|
| `labtrust validate-policy` | Validate all policy YAML/JSON against schemas. |
| `labtrust validate-policy --partner <id>` | Validate with partner overlay. |
| `labtrust forker-quickstart --out <dir>` | One shot: validate-policy, coordination security pack, lab report, risk register export. |

### 5.2 Quick sanity (benchmarks)

| Command | Description |
|---------|-------------|
| `labtrust quick-eval --seed 42 --out-dir labtrust_runs` | One episode each of throughput_sla, adversarial_disruption, multi_site_stat; summary + logs. |
| `labtrust bench-smoke --seed 42` | One episode per task (throughput_sla, stat_insertion, qc_cascade). |
| `labtrust run-benchmark --task throughput_sla --episodes 3 --seed 42 --out labtrust_runs/bench/results.json` | Run a single task; write results.json. |
| `labtrust eval-agent --task throughput_sla --episodes 1 --agent examples.external_agent_demo:SafeNoOpAgent --out labtrust_runs/agent/results.json --seed 42` | Run benchmark with an external agent. |
| `labtrust eval-agent --task throughput_sla --episodes 5 --agent labtrust_gym.baselines.marl.ppo_agent:PPOAgent --out labtrust_runs/ppo_bench/results.json --seed 42` | Run benchmark with a trained PPO model. Set `LABTRUST_PPO_MODEL` to the path to `model.zip` (e.g. `labtrust_runs/ppo_10k/model.zip`). |

Tasks: `throughput_sla`, `stat_insertion`, `qc_cascade`, `adversarial_disruption`, `multi_site_stat`, `insider_key_misuse`, `coord_scale`, `coord_risk`.

### 5.3 Export and verification

| Command | Description |
|---------|-------------|
| `labtrust export-receipts --run <episode_log.jsonl> --out <dir>` | Build EvidenceBundle.v0.1 from episode log. |
| `labtrust export-fhir --receipts <EvidenceBundle.v0.1 dir> --out <dir>` | Export FHIR R4 bundle. |
| `labtrust verify-bundle --bundle <EvidenceBundle.v0.1 dir>` | Verify one evidence bundle. |
| `labtrust verify-release --release-dir <dir>` | Verify all bundles under a release dir. |
| `labtrust ui-export --run <run_dir> --out ui_bundle.zip` | Export UI-ready zip (index, events, receipts_index, reason_codes). |

### 5.4 Security and safety

| Command | Description |
|---------|-------------|
| `labtrust run-security-suite --out <dir> --smoke --seed 42` | Security attack suite (smoke). |
| `labtrust safety-case --out <dir>` | Generate safety case under SAFETY_CASE/. |

### 5.5 Risk register

| Command | Description |
|---------|-------------|
| `labtrust export-risk-register --out <dir>` | Export RiskRegisterBundle.v0.1 to directory. |
| `labtrust export-risk-register --out <dir> --runs <run_dir>` | Include evidence from run dir(s). |
| `labtrust build-risk-register-bundle --out <path>` | Build bundle to an explicit file path. |

### 5.6 Coordination (studies and pack)

| Command | Description |
|---------|-------------|
| `labtrust run-coordination-security-pack --out <dir> --seed 42` | Coordination security pack (fixed matrix); pack_summary.csv, pack_gate.md. |
| `labtrust check-security-gate --run <dir>` | Exit 0 if all pack cells PASS; exit 1 if any FAIL. Use after run-coordination-security-pack. |
| `labtrust build-lab-coordination-report --pack-dir <dir> [--out <dir>]` | Build COORDINATION_DECISION and LAB_COORDINATION_REPORT from pack output. |
| `labtrust run-coordination-study --spec <yaml> --out <dir>` | Run coordination study (use minimal spec for smoke, e.g. tests/fixtures/coordination_study_llm_smoke_spec.yaml). |
| `labtrust summarize-coordination --in <dir> --out <dir>` | Aggregate coordination results; SOTA leaderboard. |
| `labtrust recommend-coordination-method --run <dir> --out <dir>` | Produce COORDINATION_DECISION.v0.1.json from run dir. |
| `labtrust build-coordination-matrix --run <dir> --out <path> --matrix-mode pack` | Build CoordinationMatrix from run dir. |

### 5.7 Studies and plots

| Command | Description |
|---------|-------------|
| `labtrust run-study --spec <yaml> --out <dir>` | Run study from spec. |
| `labtrust make-plots --run <dir>` | Generate figures and tables from a study run. |

### 5.8 Reproducibility and release

| Command | Description |
|---------|-------------|
| `labtrust determinism-report --task throughput_sla --episodes 2 --seed 42 --out <dir>` | Run twice in temp dirs; compare metrics and episode log hash. |
| `labtrust reproduce --profile minimal --out <dir>` | Reproducibility sweep (use LABTRUST_REPRO_SMOKE=1 for smoke). |
| `labtrust package-release --profile minimal --out <dir> --seed-base 100` | Release artifact: MANIFEST, results, receipts, figures. |
| `labtrust package-release --profile paper_v0.1 --out <dir> --seed-base 100` | Paper-ready artifact (includes SECURITY/, SAFETY_CASE/). |
| `labtrust generate-official-baselines --out <dir> --episodes 2 --seed 42 --force` | Regenerate official baselines. |
| `labtrust summarize-results --in <dir_or_file> --out <dir> --basename summary` | Aggregate results; summary_v0.2.csv, summary.md. |

### 5.9 Official pack and optional commands

| Command | Description |
|---------|-------------|
| `labtrust run-official-pack --out <dir> --smoke` | Official Benchmark Pack (smoke). Full pack is slower. |
| `labtrust train-ppo --task throughput_sla --timesteps 10000 --seed 42 --out <dir>` | PPO training (requires `.[marl]`). Throughput_sla uses `schedule_reward` for accepted QUEUE_RUN so mean reward can be non-zero. Progress bar (tqdm/rich) is optional. |
| `labtrust eval-ppo --model <dir>/model.zip --task throughput_sla --episodes 2 --seed 42 --out <path>` | PPO evaluation (requires `.[marl]`). |
| `labtrust serve --host 127.0.0.1 --port 8080` | Start HTTP server (summary/episode-log endpoints). |
| `labtrust deps-inventory --out <dir>` | Write dependency inventory (SECURITY/deps_inventory_runtime.json) to directory. |
| `labtrust transparency-log ...` | Transparency log subcommand (see CLI help). |

---

## 6. One-shot flows

**Forker quickstart (recommended after customizing policy):**  
Runs validate-policy, coordination security pack, build-lab-coordination-report, export-risk-register. Use this to get COORDINATION_DECISION and risk register in one go.

```bash
labtrust forker-quickstart --out labtrust_runs/forker_quickstart
```

Or use the script (Windows PowerShell):

```powershell
.\scripts\forker_quickstart.ps1
# Or with explicit output dir:
.\scripts\forker_quickstart.ps1 .\labtrust_runs\my_forker_run
```

**Paper quickstart (install, validate, quick-eval, package-release, verify):**  
Windows:

```powershell
.\scripts\quickstart_paper_v0.1.ps1
```

Linux/macOS:

```bash
bash scripts/quickstart_paper_v0.1.sh
```

**E2E artifacts chain (CI-style):**  
Package-release minimal, verify-release, export-risk-register. Requires bash:

```bash
make e2e-artifacts-chain
# or
bash scripts/ci_e2e_artifacts_chain.sh
```

---

## 7. Makefile shortcuts

From repo root:

| Target | Action |
|--------|--------|
| `make test` | Fast pytest (excludes some env-dependent tests). |
| `make golden` | Golden suite. |
| `make bench-smoke` | labtrust bench-smoke (needs [env]). |
| `make lint` | ruff check . |
| `make format` | ruff format . |
| `make typecheck` | mypy src/ |
| `make policy-validate` | labtrust validate-policy |
| `make e2e-artifacts-chain` | Full E2E chain (bash). |

---

## 8. Optional extras

- **MARL (PPO):** `pip install -e ".[dev,env,plots,marl]"` then `labtrust train-ppo` / `labtrust eval-ppo`.
- **Docs:** `pip install -e ".[docs]"` then `mkdocs serve` (see mkdocs.yml).
- **Live LLM:** Install `.[llm_openai]` or `.[llm_anthropic]`, set API key, use `--pipeline-mode llm_live --allow-network` on run-benchmark/quick-eval. See [LLM live](llm_live.md).

---

## 9. Troubleshooting

| Issue | Fix |
|-------|-----|
| `labtrust` not found | Use `python -m labtrust_gym.cli.main` or ensure venv is activated and `pip install -e .` was run. |
| Policy file not found | From source, policy is read from repo `policy/`. Set `LABTRUST_POLICY_DIR` if you use a different path. |
| Schema validation failed | Run `labtrust validate-policy` and fix reported files. |
| ModuleNotFoundError: pettingzoo / gymnasium | Install with env extra: `pip install -e ".[env,plots]"`. |
| Path with special characters (e.g. é in username) | Clone repo to a path without accented characters (e.g. C:\LabTrust-Gym). |
| CLI smoke test timeout | Some tests are heavy (e.g. forker-quickstart). Run with fewer tests or increase timeout. |

See [Installation](installation.md#troubleshooting) and [Troubleshooting](troubleshooting.md) for more.

---

## 10. Summary checklist

1. Clone fork, create venv, `pip install -e ".[dev,env,plots]"`, `labtrust --version`.
2. Customize `policy/` (zones, catalogue, partner overlay, coordination, risks as needed).
3. `labtrust validate-policy` [and `--partner <id>` if used].
4. `pytest -q` and/or `make test`; optionally `make golden`.
5. `labtrust quick-eval` then `labtrust bench-smoke`.
6. `labtrust forker-quickstart --out <dir>` (or run the 6-step flow from [Forker guide](FORKER_GUIDE.md)).
7. Run any of the commands in section 5 as needed (export, verify, security, safety, risk register, coordination, reproduce, package-release).
8. Optional: `pytest tests/test_cli_smoke_matrix.py` to smoke-test every CLI command; `make e2e-artifacts-chain` for full E2E.

For deeper customization (new coordination method, new risk injection, selection policy, security gate), see [Forker guide](FORKER_GUIDE.md) and the how-to docs linked there.
