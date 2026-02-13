# SOTA and state-of-the-art roadmap

This document ties together the six workstreams needed to move LabTrust-Gym a step further toward state-of-the-art: optimization completion, new SOTA coordination methods, fidelity, benchmarking coverage, engineering structure, and safety/provenance. Each section lists concrete tasks, file paths, and acceptance criteria.

---

## 1. Optimization (finish what was started)

### 1.1 Full step() dispatch (done)

**Goal:** Every `action_type` branch in `core_env.step()` is handled via `_STEP_DISPATCH` and a dedicated `_step_<action>()` method. No long `if action_type == ...` chain after the common gates.

**Files:** [src/labtrust_gym/engine/core_env.py](src/labtrust_gym/engine/core_env.py)

**Action types to move into dispatch (order preserved):**

- Already in dispatch: TICK, MOVE.
- To add: MINT_TOKEN, REVOKE_TOKEN, OPEN_DOOR (restricted-door logic stays in step() token_refs block; handler does non-restricted + restricted-without-token), CENTRIFUGE_START, QUEUE_RUN, CREATE_ACCESSION, CHECK_ACCEPTANCE_RULES, ACCEPT_SPECIMEN, HOLD_SPECIMEN, REJECT_SPECIMEN, CENTRIFUGE_END, ALIQUOT_CREATE, START_RUN, START_RUN_OVERRIDE, QC_EVENT, GENERATE_RESULT, RELEASE_RESULT, HOLD_RESULT, RERUN_REQUEST, RELEASE_RESULT_OVERRIDE, NOTIFY_CRITICAL_RESULT, ACK_CRITICAL_RESULT, ESCALATE_CRITICAL_RESULT, DISPATCH_TRANSPORT, TRANSPORT_TICK, RECEIVE_TRANSPORT, CHAIN_OF_CUSTODY_SIGN.
- Default: one handler (e.g. `_step_default`) that appends to audit and returns ACCEPTED.

**Notes:** Keep the token_refs validation block and OPEN_DOOR restricted (with token) handling in `step()` before the dispatch call so semantics stay identical. Handlers take `(event, base)` and return the step result dict.

**Acceptance:** Golden suite and `test_hashchain` / step-level tests pass; no change in step output for any scenario.

### 1.2 Observation cache

**Goal:** Avoid recomputing the same observation within a step when multiple consumers need it (e.g. env.step() and logging). Cache keyed by step index; invalidated on env.step() (next step) or env.reset().

**Files:** [src/labtrust_gym/envs/pz_parallel.py](src/labtrust_gym/envs/pz_parallel.py), [src/labtrust_gym/engine/core_env.py](src/labtrust_gym/engine/core_env.py) (optional: expose step index or cache hook).

**Tasks:**

- Add an optional observation cache on the parallel env: e.g. `_obs_cache: dict[int, dict[str, Any]]` keyed by `_step_count`, filled in `_collect_observations()` when cache miss, cleared on `reset()`.
- Document in docstring or `docs/`: when the cache is valid (same step), when it is invalidated (reset, step advance), and that callers must not mutate the returned obs.

**Acceptance:** Same obs structure and values; no regression in tests; doc updated.

**Implemented:** Observation cache is in `pz_parallel.py`: `_obs_cache_step` / `_obs_cache_data` hold the observation for the current step only. Valid when `_obs_cache_step == _step_count`; invalidated on `reset()` and when `step()` advances (next step). See `_collect_observations()` docstring for the contract (callers must not mutate returned obs).

---

## 2. SOTA coordination methods (roadmap vs implemented)

**Source:** [docs/coordination/sota_methods_at_scale.md](coordination/sota_methods_at_scale.md) (Section D).

**Status:** Implemented. `consensus_paxos_lite` and `swarm_stigmergy_priority` are in the registry, policy (coordination_methods.v0.1.yaml, method_risk_matrix.v0.1.yaml), and coordination-nightly SOTA sanity.

**Goal:** Implement one or two planned methods from the roadmap and register them so they run in the coordination study and security pack.

**Suggested first implementations (smaller scope):**

| method_id | Class | Why first |
|-----------|--------|-----------|
| `consensus_paxos_lite` | decentralized | Single global digest; bounded rounds; fits existing bus and identity. |
| `swarm_stigmergy_priority` | swarm | Priority pheromone on zone/device graph; no central plan; reuses zones. |

**Files to add/change:**

- New: `src/labtrust_gym/baselines/coordination/methods/consensus_paxos_lite.py` (or under existing methods package); implement `CoordinationMethod` (propose_actions, reset, etc.).
- New: `src/labtrust_gym/baselines/coordination/methods/swarm_stigmergy_priority.py` (stigmergy state, priority pheromone, gradient follow).
- [policy/coordination/coordination_methods.v0.1.yaml](policy/coordination/coordination_methods.v0.1.yaml): add `method_id`, `name`, `coordination_class`, `scaling_knobs`, `known_weaknesses`, `required_controls`, `compatible_injections`, `default_params`.
- [policy/coordination/method_risk_matrix.v0.1.yaml](policy/coordination/method_risk_matrix.v0.1.yaml): add (method_id, risk_id) rows and coverage.
- [src/labtrust_gym/baselines/coordination/registry.py](src/labtrust_gym/baselines/coordination/registry.py): register the new method so `run-benchmark --coord-method <id>` and study runner can resolve it.

**Acceptance:** `labtrust run-benchmark --task coord_scale --coord-method consensus_paxos_lite --episodes 1 --out /tmp/out.json` (and same for swarm_stigmergy_priority) completes; method appears in coordination study and in Layer 1 sanity script when added to the method list.

---

## 3. SOTA fidelity (algorithmic and evaluation)

**Source:** [docs/coordination_methods.md](coordination_methods.md) (SOTA fidelity checklist).

### 3.1 Fidelity notes (or tests) per method (done)

**Goal:** For each implemented coordination method, a short statement of which algorithm is implemented and how key invariants are checked.

**Tasks:**

- Add a subsection under each method in the docs, or a single doc `docs/coordination/fidelity_notes.md`: for `kernel_whca`, `ripple_effect`, `market_auction`, `gossip_consensus`, `group_evolving_experience_sharing`, `llm_repair_over_kernel_whca`, etc., document: (1) algorithm reference (e.g. WHCA*, ripple propagation), (2) key invariants (e.g. reservation table, neighbor graph), (3) where in code they are enforced or tested.
- Optionally add one test per method that asserts an invariant (e.g. ripple: propagation along edges; WHCA: reservation consistency) in `tests/`.

**Acceptance:** At least 3 methods have fidelity notes; optional tests pass.

**Implemented:** `docs/coordination/fidelity_notes.md` documents kernel_whca, kernel_auction_edf/whca, ripple_effect, group_evolving_experience_sharing, llm_repair_over_kernel_whca, and centralized/hierarchical methods with algorithm reference, invariants, and where checked.

### 3.2 Baseline and metric documentation

**Goal:** One place that defines each coordination metric and which baselines are “meaningful” for SOTA comparison.

**Files:** [docs/benchmarking_plan.md](benchmarking_plan.md), [docs/coordination_benchmark_card.md](coordination_benchmark_card.md) (or [docs/benchmark_card.md](benchmark_card.md)), and/or [docs/coordination_studies.md](coordination_studies.md).

**Tasks:**

- Add a “Coordination metrics” section: throughput_mean, violations_mean, resilience_score_mean, stealth_success_rate_mean, coordination.stale_action_rate, comm.msg_count, comm.p95_latency_ms, etc., with definitions and interpretation.
- Add a “Baselines for SOTA comparison” subsection: e.g. kernel_whca, market_auction, hierarchical_hub_rr as reference baselines; when a new method is compared, which baseline set is used in the study spec.

**Acceptance:** Doc is linked from benchmarking_plan or coordination_studies; metrics and baselines are unambiguous.

**Implemented:** `docs/coordination_benchmark_card.md` has an expanded "Metrics definitions" (perf, safety, security, robustness, coordination.*, comm.*) and a new "Baselines for SOTA comparison" section (kernel_whca, market_auction, hierarchical_hub_*, kernel_scheduler_or). `docs/benchmarking_plan.md` links to both and to `coordination/fidelity_notes.md`.

---

## 4. Benchmarking and coverage

### 4.1 Layer 2/3 in CI or release

**Goal:** Automate a small Layer 2 subset or one Layer 3 profile so “SOTA at scale” is regression-tested.

**Files:** [.github/workflows/](.github/workflows/) (new or existing workflow), [scripts/](scripts/).

**Tasks:**

- Add a job (e.g. in `coordination-nightly.yml` or a new `benchmarking-layer2.yml`): run Layer 2 coverage with a reduced matrix (e.g. one scale, one injection per method, 1 episode) or run one Layer 3 profile (e.g. `corridor_heavy`, 1 episode). Use `labtrust run-coordination-study` or `run-benchmark` with fixed seeds and store artifacts or only assert exit 0.
- Document in [docs/ci.md](ci.md): which job runs which layer and where outputs go.

**Acceptance:** Job runs on schedule or on manual dispatch; artifacts or logs available; no flake from env vars if possible (or document required vars).

### 4.2 Official baseline and DOI

**Goal:** Publish the official baseline zip (e.g. Zenodo), record the DOI, and reference it in README/docs.

**Files:** [docs/benchmarking_plan.md](benchmarking_plan.md), [README.md](README.md), [scripts/publish_baseline_artifact.sh](scripts/publish_baseline_artifact.sh) (and .ps1).

**Tasks:**

- Run `scripts/publish_baseline_artifact.sh` (or .ps1), upload the zip to Zenodo (or similar), obtain DOI.
- Add a “Published baseline” subsection in benchmarking_plan.md: DOI, link, regenerate command, citation.
- Add a short line in README (e.g. “Reproducibility”) linking to the baseline and benchmarking_plan.

**Acceptance:** DOI and link work; regenerate command reproduces the baseline.

---

## 5. Engineering and structure

### 5.1 Dedicated engine modules (state / event)

**Goal:** Align with STATUS 1.2: introduce minimal typed structures for state and event so contracts are explicit.

**Files:** [src/labtrust_gym/engine/state.py](src/labtrust_gym/engine/state.py), [src/labtrust_gym/engine/event.py](src/labtrust_gym/engine/event.py) (may already exist as stubs), [src/labtrust_gym/engine/core_env.py](src/labtrust_gym/engine/core_env.py).

**Tasks:**

- Define `InitialStateDict` (or a TypedDict/dataclass) in `state.py` with the keys used by `core_env.reset()` (e.g. system, agents, specimens, tokens, effective_policy, policy_root, timing_mode, ...). Use it in `core_env.reset(initial_state: InitialStateDict)` and in `get_initial_state` return types where appropriate.
- Define `StepEventDict` (or extend in `event.py`) with required/optional keys (event_id, t_s, agent_id, action_type, args, token_refs, key_id, signature, ...). Use it in `core_env.step(event: StepEventDict)`.
- Do not change runtime behavior: only add types and use them in signatures; keep dict-based access where needed.

**Acceptance:** mypy (or project type check) passes; core_env and callers use the new types; no behavioral change.

### 5.2 LLM “standards-of-excellence” audit

**Goal:** All LLM coordination entry points satisfy the checklist in [docs/llm_live.md](llm_live.md): schema-valid decisions, hard-fail to safe NOOP, results metadata, integration (prompt registry, tool fingerprint, transparency log).

**Files:** [src/labtrust_gym/baselines/llm/](src/labtrust_gym/baselines/llm/), [src/labtrust_gym/baselines/coordination/methods/](src/labtrust_gym/baselines/coordination/methods/) (LLM methods), [docs/llm_live.md](llm_live.md).

**Tasks:**

- List all entry points: e.g. LLMAgentWithShield, llm_central_planner, llm_hierarchical_allocator, llm_auction_bidder, llm_repair_over_kernel_whca, openai_live, anthropic_live, ollama_live.
- For each: verify (1) schema-valid decisions / invalid → NOOP, (2) timeout and refusal → NOOP and reason code, (3) provider/model/latency in results metadata, (4) prompt registry and tool fingerprint and transparency log where applicable.
- Fix gaps and add a short “LLM excellence checklist” table in llm_live.md with method/backend and status.

**Acceptance:** All listed entry points pass the checklist; doc updated.

---

## 6. Safety case and evidence

### 6.1 Risk register coverage

**Goal:** Every required risk has at least one passing scenario; enforce in CI so coverage does not regress.

**Files:** [src/labtrust_gym/export/](src/labtrust_gym/export/) (validate_coverage, risk_register_bundle), [.github/workflows/](.github/workflows/), [policy/risks/](policy/risks/).

**Tasks:**

- Run `labtrust validate-coverage --strict` (or equivalent) and fix any missing evidence (e.g. add a scenario or benchmark run that covers the risk).
- Add or keep a CI job that runs validate-coverage --strict and fails if a required risk has no evidence.

**Acceptance:** validate-coverage --strict passes; CI job runs and is documented in ci.md.

### 6.2 Paper provenance

**Goal:** Exact commands and seeds for each figure/table so reproducibility is complete.

**Files:** [docs/paper/README.md](paper/README.md) (or equivalent), [docs/PAPER_CLAIMS.md](PAPER_CLAIMS.md), [docs/reproduce.md](reproduce.md).

**Tasks:**

- Create or update `docs/paper/README.md` (or a “Figure and table provenance” section in reproduce.md): for each figure and table referenced in the paper, list the exact command(s), seeds, and output paths (e.g. `labtrust package-release --profile paper_v0.1 --out ...`, `labtrust make-plots --run ...`).
- Ensure PAPER_CLAIMS and this provenance stay in sync when new figures are added.

**Acceptance:** A reviewer can reproduce every figure/table with the documented commands and seeds.

---

## Execution order (suggested)

1. **Full step() dispatch** (1.1) – mechanical refactor; unblocks cleaner additions later.
2. **Observation cache** (1.2) – small, localized change.
3. **SOTA fidelity notes + baseline/metric docs** (3.1, 3.2) – documentation only; quick.
4. **One SOTA method** (2) – e.g. consensus_paxos_lite or swarm_stigmergy_priority.
5. **Engine state/event types** (5.1) – then LLM audit (5.2).
6. **Layer 2/3 CI** (4.1) – then baseline DOI (4.2).
7. **Risk coverage CI + paper provenance** (6.1, 6.2).

---

## References

- [coordination/sota_methods_at_scale.md](coordination/sota_methods_at_scale.md) – planned methods and method–risk mapping.
- [coordination_methods.md](coordination_methods.md) – SOTA fidelity checklist.
- [benchmarking_plan.md](benchmarking_plan.md) – Layer 1/2/3 and baseline publish.
- [llm_live.md](llm_live.md) – LLM standards-of-excellence.
- [STATUS.md](STATUS.md) – current implementation status.
- [PAPER_CLAIMS.md](PAPER_CLAIMS.md) – supported claims and provenance.
