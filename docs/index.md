# LabTrust-Gym

A multi-agent environment (PettingZoo/Gym style) for a self-driving hospital lab, with a reference **trust skeleton**: RBAC, signed actions, append-only audit log, invariants, and anomaly throttles.

This documentation reflects the **current state of the repo**: v0.1.0 contract freeze, ui-export (UI-ready bundle), quickstart scripts, paper-ready release profile, and all CLI commands. Use the nav (left) or [Installation](installation.md) to get started; [CONTRACTS](CONTRACTS.md) and [UI data contract](ui_data_contract.md) for stable interfaces.

## North star

- **Environment**: Pip-installable, standard multi-agent API (PettingZoo AEC or parallel).
- **Trust skeleton**: Roles/permissions, signed actions, hash-chained audit log, invariants, reason codes.
- **Benchmarks**: Tasks and baselines (scripted, MARL, LLM) with clear safety/throughput trade-offs.

## Principles

- **Golden scenarios drive development**: The simulator is correct when the golden suite passes.
- **Policy is data**: Invariants, tokens, reason codes, catalogue, zones live in versioned files under `policy/`.
- **Determinism**: Golden runs are deterministic (seeded RNG, no ambient randomness).
- **No silent failure**: Missing hooks or invalid data fail loudly with reason codes.

## Quick start

```bash
git clone https://github.com/fraware/LabTrust-Gym.git
cd LabTrust-Gym
pip install -e ".[dev]"
labtrust validate-policy
pytest -q
```

With PettingZoo, benchmarks, and plots:

```bash
pip install -e ".[dev,env,plots]"
LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q
labtrust run-benchmark --task TaskA --episodes 5 --seed 42 --out results.json
labtrust reproduce --profile minimal
```

Optional extras: `.[env]` (PettingZoo/Gymnasium), `.[plots]` (matplotlib), `.[marl]` (Stable-Baselines3), `.[docs]` (MkDocs + mkdocstrings).

## CLI summary

| Command | Description |
|---------|-------------|
| `--version` / `-V` | Print version and git SHA |
| `validate-policy` | Validate all policy files against JSON schemas |
| `quick-eval` | 1 episode each of TaskA, TaskD, TaskE; markdown summary and logs under `./labtrust_runs/` |
| `run-benchmark` | Run TaskA / TaskB / TaskC / TaskD / TaskE / TaskF, write results.json; optional `--llm-backend deterministic \| openai_live` (see [Live LLM](llm_live.md)) |
| `eval-agent` | Run benchmark with external agent (module:Class or module:function); write results.json (v0.2) |
| `bench-smoke` | 1 episode per task (TaskA, TaskB, TaskC) |
| `run-study` | Run study from spec (ablations → conditions) |
| `make-plots` | Generate figures and data tables from a study run |
| `reproduce --profile minimal \| full` | Reproduce minimal results + figures (TaskA & TaskC sweep + plots) |
| `export-receipts --run \<log\> --out \<dir\>` | Export Receipt.v0.1 and EvidenceBundle.v0.1 from episode log |
| `export-fhir --receipts \<dir\> --out \<dir\>` | Export FHIR R4 Bundle from receipts directory |
| `verify-bundle --bundle \<dir\>` | Verify EvidenceBundle.v0.1: manifest, schema, hashchain, invariant trace |
| `ui-export --run \<dir\> --out \<zip\>` | Export UI-ready zip (index, events, receipts_index, reason_codes) from run dir; see [UI data contract](ui_data_contract.md) |
| `package-release --profile minimal \| full \| paper_v0.1 --out \<dir\>` | Release candidate: minimal/full = reproduce + receipts + FHIR + plots; paper_v0.1 = baselines + TaskF study + FIGURES/TABLES + receipts ([paper_ready](paper_ready.md)) |
| `generate-official-baselines --out \<dir\>` | Run Tasks A–F with official baselines; write results/, summary, metadata (--episodes, --seed, --force) |
| `summarize-results --in \<paths\> --out \<dir\>` | Aggregate results.json; write summary_v0.2.csv (CI-stable), summary_v0.3.csv (paper-grade), summary.csv + summary.md |
| `determinism-report` | Run benchmark twice; produce determinism_report.md/.json; assert v0.2 metrics and log hash identical |
| `train-ppo`, `eval-ppo` | PPO training/eval (requires `.[marl]`) |

## Layout

| Path | Description |
|------|-------------|
| `policy/` | Versioned YAML/JSON: schemas (incl. receipt, evidence_bundle_manifest, fhir_bundle_export, sites_policy, key_registry, rbac_policy), emits, invariants (registry v1.0), tokens, reason_codes, zones, **keys** (key_registry), **rbac** (rbac_policy.v0.1), **sites** (sites_policy.v0.1), catalogue, stability, equipment, critical (thresholds, escalation_ladder v0.2), enforcement, studies, llm, golden, partners. Validated by `labtrust validate-policy`. |
| `src/labtrust_gym/` | Package: `config.py` (get_repo_root), `engine/` (core_env, audit_log, zones, specimens, qc, critical, queueing, devices, signatures, rbac, transport, invariants_runtime, enforcement), `policy/` (loader, validate, invariants_registry), **`export/`** (receipts, fhir_r4, **ui_export**), `runner/`, `envs/` (PettingZoo), `baselines/`, `benchmarks/`, `studies/` (study_runner, plots, reproduce, package_release), `logging/`, `cli/`, `version.py`. |
| `tests/` | Pytest: golden suite, policy validation, hashchain, tokens, zones, specimens, qc, critical, queueing, benchmarks, invariant registry, enforcement, **test_signatures_key_lifecycle** (key lifecycle), **test_llm_constrained_decoder** (constrained decode, deterministic baseline), signatures, rbac, transport, export_receipts, fhir_export, package_release, study runner, plots, reproduce smoke, adversary, marl smoke, llm agent mock. |
| `docs/` | Architecture, policy pack, invariants & enforcement, benchmarks, benchmark_card, studies, reproduce, fhir_export, frozen_contracts, **ui_data_contract**, **CONTRACTS** (release freeze), PettingZoo API, CI, threat model, MARL/LLM baselines, STATUS. MkDocs site (build with `.[docs]`). CITATION.cff at repo root. |

## What's frozen

Contracts and schema versions that define correctness (anti-regression backbone): **[Frozen contracts](frozen_contracts.md)** — runner output contract, queue contract (v0.1), invariant registry schema (v1.0), enforcement map schema (v0.1), study spec schema (v0.1).

## See also

- [Installation](installation.md) — pip, quick-eval, quickstart script, troubleshooting
- [Architecture](architecture.md)
- [Policy pack and schemas](policy_pack.md)
- [Frozen contracts](frozen_contracts.md) · [Public contract freeze (v0.1.0)](CONTRACTS.md)
- [UI data contract](ui_data_contract.md) — ui-export bundle format; UI consumes ui-export output, not raw logs
- [Invariants and enforcement](invariants_registry.md) · [Enforcement](enforcement.md)
- [PettingZoo API](pettingzoo_api.md)
- [Benchmarks](benchmarks.md) · [Benchmark card](benchmark_card.md) · [Studies and plots](studies.md) · [Reproduce](reproduce.md) · [Paper-ready release](paper_ready.md)
- [FHIR R4 export](fhir_export.md) · [Evidence verification](evidence_verification.md)
- [MARL baselines](marl_baselines.md) · [LLM baselines](llm_baselines.md) · [Live LLM benchmark mode](llm_live.md)
- [CI](ci.md) · [STATUS](STATUS.md)
- [Improvements before online / non-deterministic](IMPROVEMENTS_BEFORE_ONLINE.md) — checklist (stability, code optimization, testing, docs, pre-online readiness)
- [API Reference](api/index.md) (auto-generated)
