# LabTrust-Gym: 3-Minute Progress Update

This document provides a detailed progress update suitable for a short presentation and for incorporation into the repository documentation. It reflects the state of the project as of the v0.1.0 contract freeze and current main branch on 02/02/2026.

---

## 1. Project overview and north star

**LabTrust-Gym** is a multi-agent environment (PettingZoo/Gym style) for a self-driving hospital lab. It combines a **simulation environment** with a **reference trust skeleton**: RBAC, signed actions, append-only hash-chained audit log, invariants, reason codes, and anomaly throttles.

**North star:**

- **Environment:** Pip-installable, standard multi-agent API (PettingZoo AEC or parallel).
- **Trust skeleton:** Roles and permissions, signed actions, hash-chained audit log, invariants, reason codes.
- **Benchmarks:** Tasks and baselines (scripted, MARL, LLM) with clear safety/throughput trade-offs.

**Principles:** Golden scenarios drive development; policy is data (versioned under `policy/`); determinism for regression and reproduction; no silent failure (missing hooks or invalid data fail loudly with reason codes). High-level pipeline and HSL lab topology: [Architecture diagrams](diagrams.md).

---

## 2. Release state and contract freeze

- **Version:** `labtrust --version` prints **v0.1.0** plus git SHA. The project is at **v0.1.0 release** with a **public contract freeze** (see [CONTRACTS.md](CONTRACTS.md)).
- **Packaging:** Pip-installable from PyPI: `pip install labtrust-gym[env,plots]`. Optional extras: `[env]` (PettingZoo/Gymnasium), `[plots]` (matplotlib), `[marl]` (Stable-Baselines3), `[docs]` (MkDocs). Release workflow builds sdist and wheel on tag `v*`; policy is copied into the package so the wheel ships policy.
- **Frozen contracts:** Runner output contract (v0.1), queue contract (v0.1), invariant registry (v1.0), enforcement map (v0.1), receipt and evidence bundle manifest (v0.1), FHIR bundle export (v0.1), results semantics (v0.2; v0.3 extensible only), key registry (v0.1), RBAC policy (v0.1), sites policy (v0.1). These define correctness; they are not weakened without a design change and version bump.
- **Quick validation:** After install, `labtrust quick-eval` runs one episode each of TaskA, TaskD, and TaskE, prints a markdown summary, and writes logs under `./labtrust_runs/`. `labtrust validate-policy` validates all policy YAML/JSON against JSON schemas.

---

## 3. Trust skeleton and engine

**Implemented and aligned with design:**

- **Policy loading and validation:** All policy files (emits, zones, reason codes, tokens, dual approval, critical, equipment, golden, invariant registry, enforcement map, runner contract, catalogue, coordination, safety case, official pack, keys, RBAC, sites, etc.) have JSON schemas under `policy/schemas/` and are validated by `labtrust validate-policy`. Partner overlays (e.g. `policy/partners/hsl_like/`) merge over base policy for critical, stability, enforcement, equipment.
- **Audit and hashchain:** Canonical event serialization, SHA-256 hash chain, append-only log. Chain break triggers forensic freeze; all subsequent steps BLOCKED with AUDIT_CHAIN_BROKEN (golden scenario GS-022).
- **RBAC:** Roles (allowed_actions, allowed_zones, allowed_devices), agent-to-role bindings. RBAC is the first gate in step; BLOCKED with RBAC_ACTION_DENY / RBAC_ZONE_DENY / RBAC_DEVICE_DENY when violated. Token cannot bypass RBAC (GS-RBAC-029).
- **Signatures and key registry:** Ed25519 keys with optional lifecycle: status (ACTIVE, REVOKED, EXPIRED), not_before_ts_s / not_after_ts_s. Verification enforces key existence, ACTIVE status, validity window, agent binding, and role match (INV-SIG-002). Reason codes: SIG_MISSING, SIG_INVALID, SIG_KEY_REVOKED, SIG_KEY_EXPIRED, SIG_KEY_NOT_YET_VALID, SIG_ROLE_MISMATCH. TaskF runs with strict_signatures; phase 4 uses revoked key and is BLOCKED with SIG_KEY_REVOKED.
- **Tokens:** Dual-approval validation, lifecycle (ACTIVE to CONSUMED/REVOKED/EXPIRED), replay protection. Golden scenarios GS-010–GS-013 cover same-approver reject, expired, replay, revoked.
- **Zones and doors:** Zone graph, device placement, restricted doors (token required), door-open-too-long alarm and zone freeze (GS-008, GS-009, GS-020).
- **Specimens:** Acceptance rules, hold/reject with reason codes (e.g. citrate underfill, ID mismatch, leaking). HOLD_SPECIMEN without reason_code is BLOCKED (GS-003–GS-005, GS-021).
- **QC and result gating:** Device QC state, RELEASE_RESULT blocked until QC pass; drift override path with token and disclaimer flag (GS-014, GS-015).
- **Critical results (v0.2 escalation ladder):** Classify CRIT_A/CRIT_B; notify, ACK with required fields and readback when required; escalate in tier order; timeout triggers escalation. RELEASE_RESULT blocked until compliant ACK (GS-016–GS-018, GS-CRIT-023–025).
- **Catalogue and stability:** Panel lookup, stability windows, temp checks. START_RUN gated by stability and temp; TIME_EXPIRED / TEMP_OUT_OF_BAND BLOCKED unless override with dual-approval token (GS-001, GS-006, GS-007).
- **Co-location:** START_RUN and START_RUN_OVERRIDE require agent zone equals device zone; otherwise BLOCKED RC_DEVICE_NOT_COLOCATED (GS-019).
- **Queueing (contract frozen):** Per-device queue, STAT/URGENT/ROUTINE ordering, queue_head(device_id), QUEUE_RUN and START_RUN consume semantics per [queue_contract.v0.1.md](queue_contract.v0.1.md) (GS-002).
- **Transport (multi-site):** Sites policy, routes, DISPATCH_TRANSPORT, TRANSPORT_TICK, RECEIVE_TRANSPORT, CHAIN_OF_CUSTODY_SIGN. Temp excursion and chain-of-custody violations BLOCKED with reason codes and invariants INV-COC-001, INV-TRANSPORT-001 (GS-TRANSPORT-001, GS-TRANSPORT-002, GS-COC-003).
- **Invariant registry (v1.0) and enforcement:** Post-step invariant checks; enforcement map (throttle, kill_switch, freeze_zone, forensic_freeze) with escalation. Step output includes violations and enforcements.
- **Runtime control (shift-change):** Control actions (agent_id SYSTEM): UPDATE_ROSTER (merge roster into in-memory RBAC), INJECT_SPECIMEN (add specimen at runtime). Policy on disk unchanged. Golden scenario GS-SHIFT-CHANGE-001: mid-episode role swap, STAT specimen injection, queue contract and RBAC behaviour with post-shift keys; strict signatures.

**Golden suite:** 34 scenarios. Full suite passes with `LABTRUST_RUN_GOLDEN=1` (real engine). Covers pipeline, queue, acceptance, stability, zones, tokens, QC, critical, signatures, RBAC, transport, export, shift-change. See [STATUS.md](STATUS.md) for the full table.

---

## 4. Benchmarks, baselines, and artifacts

**Tasks:** TaskA (routine pipeline), TaskB, TaskC, TaskD (adversarial disruption), TaskE (multi-site STAT), TaskF (insider and key misuse: forbidden action, forged signature, replay, revoked key, token misuse), TaskG_COORD_SCALE (coordination at scale), TaskH_COORD_RISK (coordination under risk injections).

**Baselines:** Scripted ops, scripted runner, adversary, insider (TaskF), LLM (constrained decoder, DeterministicConstrainedBackend as official offline baseline; optional OpenAI/Ollama live with `--pipeline-mode llm_live --allow-network`), MARL/PPO (optional `.[marl]`). Coordination methods (e.g. centralized_planner, hierarchical_hub_rr, kernel_whca, kernel_auction_whca_shielded, llm_constrained, marl_ppo) with policy-driven method and risk registries.

**Metrics and results:** Results semantics v0.2 (CI-stable); v0.3 adds quantiles and 95% CI for paper-grade reporting. Summary tables: summary_v0.2.csv, summary_v0.3.csv, summary.md. Official baselines v0.2 are canonical; frozen results in `benchmarks/baselines_official/v0.2/`. Coordination study outputs: summary_coord.csv, pareto.md, resilience and security metrics (e.g. attack_success_rate, stealth, attribution, blast radius).

**Pipelines:** Default is **deterministic** (no network, scripted only). Optional `llm_offline` (LLM interface, deterministic backend) and `llm_live` (requires `--allow-network`). Every run records pipeline_mode, llm_backend_id, llm_model_id, allow_network in results and UI export.

**Official Benchmark Pack v0.1:** Single command `labtrust run-official-pack --out <dir> --seed-base N` produces one folder with: baselines/results/ (TaskA–TaskH per baseline), SECURITY/ (attack suite and securitization packet), SAFETY_CASE/, TRANSPARENCY_LOG/, pack_manifest.json, PACK_SUMMARY.md. Smoke mode (fewer episodes, security smoke-only) is default for fast validation.

**Paper-ready artifact:** `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>` builds: official baselines (Tasks A–F), TaskF strict_signatures study, combined summary and tables, representative run per task with receipts and verify-bundle, FIGURES/, TABLES/, SECURITY/ (attack suite smoke and securitization packet), SAFETY_CASE/, COORDINATION_CARD.md and frozen _coordination_policy/, RELEASE_NOTES.md, MANIFEST.v0.1.json, BENCHMARK_CARD.md. Offline and deterministic with fixed seed. Quickstart: `scripts/quickstart_paper_v0_1.sh` or `scripts/quickstart_paper_v0.1.ps1`.

**Security attack suite and securitization:** Policy-driven suite (`policy/golden/security_attack_suite.v0.1.yaml`) maps risks to controls and executable scenarios (prompt-injection, tool, coordination, memory, etc.). `labtrust run-security-suite --out <dir>` writes SECURITY/attack_results.json and securitization packet (coverage.json, coverage.md, reason_codes.md, deps_inventory_runtime.json). Integrated into paper_v0.1 and run-official-pack. Smoke mode is CI-runnable.

**Safety case:** Claims in `policy/safety_case/claims.v0.1.yaml`; generator produces SAFETY_CASE/safety_case.json and safety_case.md (claim to control, test, artifact, verification command). CLI `labtrust safety-case --out <dir>`; included in package-release paper_v0.1 and run-official-pack.

**Export and verification:** Receipt.v0.1, EvidenceBundle.v0.1 (manifest, hashchain proof, invariant trace, optional tool/RBAC/coordination/memory policy fingerprints). FHIR R4 Bundle export. `labtrust export-receipts`, `labtrust export-fhir`, `labtrust verify-bundle`. UI export: `labtrust ui-export --run <dir> --out ui_bundle.zip` produces index.json, events.json, receipts_index.json, reason_codes.json per [UI data contract](ui_data_contract.md).

**Coordination red team:** Injections v0.2 (success/detection/containment definitions), adversary strategies in baselines, metrics: stealth_success_rate, time_to_attribution_steps, blast_radius_proxy. Coordination identity (SignedMessageBus, replay protection), tool sandbox, memory hardening (authenticated writes, poison filtering). COORD_* and related reason codes; verify-bundle optional coordination_policy_fingerprint, memory_policy_fingerprint.

---

## 5. Reproducibility and CLI summary

**Reproduce:** `labtrust reproduce --profile minimal` (or full) runs TaskA and TaskC sweep and generates figures. `labtrust determinism-report` runs the benchmark twice in fresh temp dirs and asserts v0.2 metrics and episode log hash identical.

**Key CLI commands:** validate-policy, quick-eval, run-benchmark (--task, --episodes, --llm-backend, --coord-method, --injection), eval-agent, bench-smoke, export-receipts, export-fhir, verify-bundle, run-security-suite, safety-case, run-official-pack, ui-export, run-study, run-coordination-study, make-plots, package-release (minimal | full | paper_v0.1), generate-official-baselines, summarize-results, determinism-report, train-ppo / eval-ppo (with [marl]), serve (online HTTP with auth and rate limits). See README and [index.md](index.md) for the full list.

**CI:** `.github/workflows/ci.yml` (ruff, mypy, pytest, policy validation; optional bench-smoke and coordination-smoke). Release workflow on tag; package-release-nightly for scheduled artifact build.

---

## 6. What remains (prioritized)

- **Optional engine refactor:** state.py, event.py, errors.py as dedicated modules (state is currently dict-based in core_env and sub-stores).
- **B003 public-release redaction:** Not yet implemented for public-release redaction of sensitive data.
- **Improvements before online:** See [IMPROVEMENTS_BEFORE_ONLINE.md](IMPROVEMENTS_BEFORE_ONLINE.md): stability (ui_fixtures, long tests), code optimization (policy loading in hot path, large JSONL, summarize/export), testing (pytest timeout, coverage, CI), documentation, pre-online readiness.
- **Published benchmark results:** Empirical results can be published as needed; tooling (summarize-results, official baselines v0.2) is in place.
- **Jupyter notebooks:** None in repo; MkDocs site and API reference (mkdocstrings) are available.

---

## 7. Summary table (high level)

| Area | Status |
|------|--------|
| Policy load/validate, schemas | Implemented; all policy files validated |
| Golden runner, 34 scenarios | Full suite passes with real engine |
| Audit, hashchain, forensic freeze | Implemented |
| RBAC, signatures, key lifecycle | Implemented; TaskF strict_signatures |
| Tokens, zones, specimens, QC, critical | Implemented |
| Catalogue, stability, co-location, queueing | Implemented; queue contract v0.1 frozen |
| Transport, invariant registry, enforcement | Implemented |
| Runtime control (shift-change) | Implemented; GS-SHIFT-CHANGE-001 |
| PettingZoo API, baselines (scripted, adversary, LLM, MARL, coordination) | Implemented |
| Tasks A–H, metrics v0.2/v0.3 | Implemented |
| Official pack, paper_v0.1, security suite, safety case | Implemented |
| Export (receipts, FHIR, UI), verify-bundle | Implemented |
| PyPI packaging, quick-eval, versioning | Implemented |
| Docs (MkDocs, STATUS, CONTRACTS, guides) | Implemented |

This progress update is intended for presentation use and for inclusion in the repository documentation. For the authoritative current state of the repo, see [STATUS.md](STATUS.md). For contract and release details, see [CONTRACTS.md](CONTRACTS.md) and [paper_ready.md](paper_ready.md).
