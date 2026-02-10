# LabTrust-Gym: End-to-End Pipeline Overview

This document describes what the repo does from end to end: the simulator, trust model, main capabilities, and how the pieces fit together. It stays at the "what it provides" level; implementation details live in the other docs and the codebase.

---

## What the repo is

**LabTrust-Gym** is a multi-agent simulation environment (Gym/PettingZoo style) for a **self-driving hospital lab**. It provides:

- **North star**: A pip-installable environment with a reference **trust skeleton** (RBAC, signed actions, hash-chained audit log, invariants, anomaly throttles) and **benchmarks** (tasks and baselines with clear safety/throughput trade-offs).
- **Policy as data**: Invariants, tokens, zones, equipment, coordination methods, security scenarios, and study specs live under `policy/` and are validated against schemas. The simulator is correct when the golden suite passes; runs are deterministic by default.

So at the highest level: you run a **hospital lab simulator** under **versioned policy**, execute **tasks** and **coordination/security experiments**, and get **metrics, evidence, and reports** you can use for benchmarking, safety cases, and risk/evidence bundles.

---

## The simulator and trust skeleton

- **Core**: Agents (scripted, LLM, or MARL) operate in a lab world: zones, devices, specimens, QC, critical results, queueing, multi-site transport. The engine steps the simulation, enforces invariants, and records an append-only, hash-chained audit log.
- **Trust**: Actions can be signed (Ed25519); keys have lifecycle (ACTIVE/REVOKED/EXPIRED). There is RBAC, reason codes, and runtime controls (throttle, kill switch, forensic freeze). Policy defines what is allowed and how violations are treated.
- **Pipeline modes**: Runs can be **deterministic** (no network, scripted/LLM stub only), **llm_offline** (LLM interface but deterministic backend), or **llm_live** (real API calls; opt-in with `--allow-network`). Default is offline so CI and reproduction do not hit APIs.

So the repo gives you a **controllable, auditable lab simulation** that can be driven by scripted baselines or by LLM/MARL agents, with security and coordination built into the model.

---

## What the repo can do (capabilities)

Grouped by "what you get out of it."

### 1. Policy and sanity

- **validate-policy**: Check all policy YAML/JSON under `policy/` against schemas. Run this before any heavy workflow.
- **quick-eval**: Run one episode each of a few core tasks (throughput_sla, adversarial_disruption, multi_site_stat), print a markdown summary, and write logs under `./labtrust_runs/`. Confirms the stack works.

### 2. Single benchmark runs

- **run-benchmark**: Run one task (e.g. throughput_sla through coord_risk) for a given number of episodes, with optional scale, timing, coordination method, and injection. Writes `results.json` (v0.2 metrics). Use this to try one method, one scale, or one attack (e.g. coord_risk with a specific injection).
- **eval-agent**: Same idea but with an external agent (module:Class or module:function). Useful for plugging in custom controllers.

So: **one task, one (or few) conditions, one output file**. Good for debugging, sanity, or single-point comparisons.

### 3. Coordination studies (scale x method x injection)

- **run-coordination-study**: Run a **full matrix** from a spec: for each cell (scale x method x injection) it runs coord_risk (or the spec-defined task), writes per-cell results, then aggregates:
  - `summary/summary_coord.csv` (metrics per method, scale, injection),
  - `summary/pareto.md` (per-scale Pareto and robust winner),
  - and optionally SOTA leaderboard / method-class comparison if you run the summarizer next.

You can use a **deterministic** spec (no network) or an **LLM-live** spec with `--llm-backend openai_live` (or similar) and `--allow-network`. This is the main way to compare many coordination methods across scales and attacks in one go.

### 4. Coordination security pack (regression matrix)

- **run-coordination-security-pack**: Runs a **fixed** matrix (scale x method x injection), one episode per cell, **deterministic** only. It does not use live LLMs. Outputs:
  - `pack_summary.csv` (one row per cell: perf, safety, sec metrics),
  - `pack_gate.md` (PASS/FAIL/not_supported per cell from gate rules),
  - `SECURITY/coordination_risk_matrix.csv` and `.md` (method x injection x phase outcomes).

You can narrow the matrix with **--matrix-preset hospital_lab** (lab-tailored scales/methods/injections) or with `--methods-from` / `--injections-from`. This is the **internal regression and security-stress** path: fast, repeatable, no API cost.

### 5. Summarize, recommend, and lab report (hospital lab flow)

After you have either a coordination study output or a pack output:

- **summarize-coordination**: Reads `summary_coord.csv` or `pack_summary.csv` from a directory, writes under `--out`:
  - SOTA leaderboard (per-method means: throughput, violations, resilience, stealth),
  - Method-class comparison (centralized vs ripple vs auctions vs kernel_schedulers, etc.),
  - Optionally a **by-phase** view when the source has `application_phase`, plus a short **source note** in the MD (e.g. "Source: pack_summary.csv. This run includes an application_phase dimension.").

- **recommend-coordination-method**: Reads the same run dir (first of `pack_summary.csv` or `summary/summary_coord.csv`), applies the **selection policy** (hard constraints + objective, e.g. maximize resilience or throughput), and writes:
  - `COORDINATION_DECISION.v0.1.json` and `COORDINATION_DECISION.md`: **chosen method per scale** (or "no admissible method").

- **build-lab-coordination-report**: **One command** that takes a pack output dir and:
  - Runs summarize-coordination (if needed),
  - Runs recommend-coordination-method,
  - Optionally builds the CoordinationMatrix in pack mode (`--include-matrix`) and adds it to the report,
  - Writes **LAB_COORDINATION_REPORT.md**: scope, recommended method per scale, artifact table (pack_gate, risk matrix, leaderboard, method-class comparison, decision, optional matrix), "how to interpret," and "next steps."

So: **pack (or study) → summarize → recommend → one lab report**. That report is the **stakeholder-facing bundle** for "what we ran, what passed, and which method to use per scale."

### 6. Coordination matrix (scores and recommendations per scale)

- **build-coordination-matrix**: Builds **CoordinationMatrix v0.1** from a coordination run dir: clean + attacked metrics, normalization, scoring (e.g. cq_score, ar_score), and per-scale recommendations (ops_first / sec_first / balanced).  
  - **llm_live mode** (default): Expects an llm_live run with `summary_coord.csv`; uses it as the canonical clean source.  
  - **pack mode** (`--matrix-mode pack`): Allows a pack-only dir (no `summary_coord.csv`); derives clean metrics from `pack_summary.csv` baseline rows and still produces the same schema.  
  So you can get the same matrix structure from either a full study or from a pack run.

### 7. Security attack suite

- **run-security-suite**: Runs the **golden security suite** (prompt-injection, tool/coord/memory attacks, etc.) from `policy/golden/security_attack_suite.v0.1.yaml`. Writes:
  - `SECURITY/attack_results.json` (per-attack pass/fail, duration, errors),
  - Securitization packet: `SECURITY/coverage.json`, `coverage.md`, `reason_codes.md`, `deps_inventory.json`.

It is **deterministic** for a fixed seed and policy; smoke mode runs only smoke-marked attacks (CI-friendly). This is the **security regression and coverage** path independent of coordination.

### 8. Official benchmark pack (single artifact for researchers)

- **run-official-pack**: Runs a **curated pack** (tasks, scales, baselines, coordination methods, security suite, safety case, transparency log) and writes everything into **one output dir** that external researchers can run and compare against. Options include smoke vs full, deterministic vs llm_live, and seed.  
  So: **one command → one folder** that represents "the official benchmark result" for a given config.

### 9. Risk register (evidence bundle for risks and controls)

- **export-risk-register** / **build-risk-register-bundle**: Build **RiskRegisterBundle.v0.1** from policy and run dir(s). The bundle ties **risks** (from risk registry) to **controls** and **evidence** (SECURITY/, summary/, SAFETY_CASE/, MANIFEST, etc.). Missing evidence is explicit (stubs). Used for review, coverage, and UIs that show "risk → control → test → artifact."  
  So: **runs + policy → one JSON bundle** that answers "what evidence do we have for each risk?"

### 10. Export and verification

- **export-receipts**: Turn an episode log into Receipt.v0.1 and EvidenceBundle.v0.1.
- **export-fhir**: Export a FHIR R4 Bundle from a receipts dir.
- **ui-export**: Produce a UI-ready zip (index, events, receipts_index, reason_codes) for a run dir.
- **verify-bundle**: Verify a **single** EvidenceBundle.v0.1 directory (manifest, schema, hash chain, invariant trace). The `--bundle` argument must be the path to an EvidenceBundle.v0.1 directory (one that contains `manifest.json`), e.g. `release/receipts/taska_cond_0/EvidenceBundle.v0.1`. The **release root** (the output of package-release, which contains `MANIFEST.v0.1.json` and `receipts/`) is **not** valid for `--bundle`; use **verify-release** for that.
- **verify-release**: Verify **all** EvidenceBundle.v0.1 directories under a release. Pass the release directory (output of package-release): `labtrust verify-release --release-dir <path>`. The command discovers every `receipts/*/EvidenceBundle.v0.1`, runs the same checks as verify-bundle on each, and exits non-zero if any fail. Use this to verify a minimal (or full) release in one step.

So: **run → receipts/FHIR/UI bundle**; **verify-bundle** checks one EvidenceBundle; **verify-release** checks every EvidenceBundle in a release; both ensure bundles are intact and consistent with policy.

### 11. Plots, reproduce, and release

- **make-plots**: Generate figures and data tables from a study run (e.g. coordination: resilience vs p95_tat, attack_success_rate).
- **reproduce**: Reproduce minimal (or full) results + figures with a fixed profile.
- **package-release**: Build a **release candidate**: reproduce + receipts + FHIR + plots + MANIFEST + benchmark card + summary table. The **paper_v0.1** profile adds security suite, safety case, coordination card, and frozen coordination policy for a paper-ready artifact.

So: **study/release dir → figures and tables**; **reproduce** gives a fixed sweep; **package-release** gives a full artifact (including paper-ready with security and safety).

---

## How the pieces connect (end-to-end flows)

### Hospital lab flow (recommended path)

1. **Run matrix**:  
   `labtrust run-coordination-security-pack --out <dir> [--matrix-preset hospital_lab]`  
   → `pack_summary.csv`, `pack_gate.md`, `SECURITY/coordination_risk_matrix.*`.

2. **Build report**:  
   `labtrust build-lab-coordination-report --pack-dir <dir> [--out <dir>] [--matrix-preset hospital_lab] [--include-matrix]`  
   → summarize + recommend + optional matrix + **LAB_COORDINATION_REPORT.md** and all artifacts in one tree.

3. **Use the decision**:  
   Open **COORDINATION_DECISION.v0.1.json** / **.md** for the chosen method per scale; use **LAB_COORDINATION_REPORT.md** for the full story (gate, risk matrix, leaderboard, decision, next steps).

So: **pack → build-lab-coordination-report → use COORDINATION_DECISION and lab report.**

### Forker copy-paste sequence

The same six-step flow works from a clean clone (or a forker's repo) with no code changes. Replace `<dir>`, `<dir2>`, `<dir3>` with real paths.

1. `labtrust validate-policy` (optionally `--partner hsl_like`)
2. `labtrust run-coordination-security-pack --out <dir> [--matrix-preset hospital_lab]`
3. `labtrust build-lab-coordination-report --pack-dir <dir> [--out <dir>]`
4. Open `COORDINATION_DECISION.v0.1.json` / `LAB_COORDINATION_REPORT.md` for recommended method per scale
5. `labtrust export-risk-register --out <dir2> --runs <dir>`
6. Optional: `labtrust run-official-pack --out <dir3>`, then `labtrust export-risk-register --out <dir2> --runs <dir3>`

See [Forker guide](FORKER_GUIDE.md) for partner overlays, coordination methods/scales, and extending the repo.

### Full coordination study flow (research / LLM comparison)

1. **Run study**:  
   `labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out <dir>`  
   (or the llm_live spec with `--llm-backend` and `--allow-network`).  
   → cells, `summary/summary_coord.csv`, pareto.

2. **Summarize** (if not already done):  
   `labtrust summarize-coordination --in <dir> --out <dir>`  
   → SOTA leaderboard, method-class comparison.

3. **Recommend**:  
   `labtrust recommend-coordination-method --run <dir> --out <dir>`  
   → COORDINATION_DECISION.*.

4. **Optional matrix** (for llm_live or pack):  
   `labtrust build-coordination-matrix --run <dir> --out <dir>`  
   (use `--matrix-mode pack` if the run is pack-only).  
   → CoordinationMatrix v0.1 (scores and ops_first/sec_first/balanced per scale).

So: **study → summarize → recommend → (optional) matrix.**

### Paper / release flow

1. **Release artifact**:  
   `labtrust package-release --profile paper_v0.1 --out <dir>`  
   → Reproduce + SECURITY/ + SAFETY_CASE/ + MANIFEST + figures + coordination card, etc.

2. **Risk register from that artifact**:  
   `labtrust export-risk-register --out <dir> --runs <release_dir>`  
   → RISK_REGISTER_BUNDLE.v0.1.json with evidence links and missing stubs.

So: **package-release → export-risk-register** gives a **single evidence bundle** for the release.

---

## Summary table (what you get)

| Goal | Main command(s) | Main outputs |
|------|------------------|--------------|
| Check policy and stack | validate-policy, quick-eval | Schema errors; markdown summary + logs |
| Single task / method / injection | run-benchmark, eval-agent | results.json |
| Full coordination matrix (study) | run-coordination-study | cells/, summary_coord.csv, pareto.md |
| Security regression (coord) | run-coordination-security-pack | pack_summary.csv, pack_gate.md, SECURITY/coordination_risk_matrix.* |
| Aggregate and rank methods | summarize-coordination, recommend-coordination-method | SOTA leaderboard, method-class comparison, COORDINATION_DECISION.* |
| One lab report bundle | build-lab-coordination-report | LAB_COORDINATION_REPORT.md + summarize + recommend (+ optional matrix) |
| Matrix (scores per scale) | build-coordination-matrix | coordination_matrix.v0.1.json |
| Security coverage | run-security-suite | SECURITY/attack_results.json, coverage, securitization packet |
| Researcher-facing pack | run-official-pack | One dir: tasks, SECURITY/, SAFETY_CASE/, transparency log |
| Risk/evidence view | export-risk-register | RISK_REGISTER_BUNDLE.v0.1.json |
| Verify release | verify-release (all bundles), verify-bundle (single) | Per-bundle PASS/FAIL; E2E chain uses verify-release |
| Release / paper | package-release, export-risk-register | Full artifact; risk bundle |

---

## Where to read next

- **Coordination**: [Coordination studies](coordination_studies.md), [Lab coordination report](lab_coordination_report.md), [Benchmarking plan](benchmarking_plan.md).
- **Security**: [Security attack suite](security_attack_suite.md).
- **Release and risk**: [Risk register](risk_register.md), [Official benchmark pack](official_benchmark_pack.md), [Paper ready](paper_ready.md).
- **Environment and API**: [Architecture](architecture.md), [PettingZoo API](pettingzoo_api.md), [LLM live](llm_live.md).
