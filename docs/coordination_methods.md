# Coordination Methods

Coordination methods produce per-agent actions for the PettingZoo Parallel env and are compared at scale in TaskG_COORD_SCALE and TaskH_COORD_RISK. Each method implements the same interface and runs deterministically when using the deterministic backend. The registry is defined in `policy/coordination/coordination_methods.v0.1.yaml`; risk coverage is in `policy/coordination/method_risk_matrix.v0.1.yaml` and `policy/risks/risk_registry.v0.1.yaml`.

## Interface

- **CoordinationMethod**: `method_id`, `reset(seed, policy, scale_config)`, `propose_actions(obs, infos, t) -> dict[agent_id, action_dict]`, optional `on_step_result(step_outputs)`. Kernel-composed methods also implement `step(context) -> (actions, CoordinationDecision)` for decision tracing.
- **action_dict**: At least `action_index` (0=NOOP, 1=TICK, 2=QUEUE_RUN, 3=MOVE, 4=OPEN_DOOR, 5=START_RUN); optionally `action_type`, `args`, `reason_code`, `token_refs` for engine events. Actions are schema-valid and do not bypass RBAC or signature rules.

## Coordination kernel (ALLOCATION, SCHEDULING, ROUTING)

Methods can be implemented as a **composition of three components**, so allocation, scheduling, and routing are cleanly separated and swappable:

- **Allocator**: Chooses which agent(s) own which work items (specimens, runs, transports). Output: `AllocationDecision` (assignments, explain).
- **Scheduler**: Sequences owned work items per agent/device with deadlines and priorities. Output: `ScheduleDecision` (per-agent order, explain).
- **Router**: Produces safe movement/zone transitions (or reservations) to execute the scheduled steps. Output: `RouteDecision` (per-agent action_type and args, explain).

**KernelContext** provides a state snapshot (obs, infos, t), policy, scale config, seed, and a seeded RNG so every tie-break is deterministic. **compose_kernel(allocator, scheduler, router, method_id)** returns a `CoordinationMethod` that:

1. In each step, runs allocator -> scheduler -> router.
2. Builds a **CoordinationDecision** with stable hashes (state_hash, allocation_hash, schedule_hash, route_hash) and compact explain summaries.
3. Emits **COORD_DECISION** (in the audit/step results) with method_id, step_idx, seed, hashes, and explain fields (no large blobs).

Swapping only the router changes **route_hash** but not allocation_hash or schedule_hash; swapping the allocator changes allocation_hash and downstream hashes. This supports ablation and comparison of components. See `src/labtrust_gym/baselines/coordination/coordination_kernel.py`, `decision_types.py`, `compose.py`, and `kernel_components.py`.

### Example: kernel_centralized_edf

- **Allocator**: `CentralizedAllocator` (greedy by priority and colocation; compute_budget knob).
- **Scheduler**: `EDFScheduler` (earliest-deadline-first per agent; deterministic tie-break).
- **Router**: `TrivialRouter` (BFS move toward goal zone or START_RUN when colocated).

Run with: `labtrust run-benchmark --task TaskG_COORD_SCALE --coord-method kernel_centralized_edf --episodes 1 --seed 42 --out results.json`. Determinism: same seed yields identical decision hashes and per-agent actions; see `tests/test_coordination_kernel_determinism.py` and `tests/test_coordination_kernel_composition.py`.

## Event-sourced blackboard and partial observability

Instead of "agents magically see global state", TaskG/TaskH can use an explicit **BlackboardLog** and **ViewReplicas** so coordination is evaluated under configurable comms semantics:

- **BlackboardLog** (`src/labtrust_gym/coordination/blackboard.py`): Append-only events (facts) with deterministic ordering and replay. Each event has id, t_event, t_emit, type, payload_hash, payload_small. Head hash chains events for integrity.
- **ViewReplica** (`views.py`): Per-agent local view that lags behind the global log. `apply(event)` updates from a delivered event; `snapshot()` returns minimal state (queue_heads, zone_occupancy, device_status, specimen_statuses) used by policies.
- **CommsModel** (`comms_model.py`): Delivers log events to view replicas with configurable delay (seeded), drop_rate, reorder_window, duplicate_rate. **Perfect** mode (default) delivers all events immediately with no loss or reorder.

The **BlackboardHarness** (`harness.py`) is created when running TaskG/TaskH with a coordination method: each env step, facts are derived from engine step outputs and appended to the log; CommsModel delivers new events to replicas; replicas apply and expose snapshots. **KernelContext** receives optional `global_log` and `view_snapshots` so centralized methods can read from the full log and decentralized methods from per-agent views.

**Comms risk injections** (policy-driven): INJ-COMMS-DELAY-001, INJ-COMMS-DROP-001, INJ-COMMS-REORDER-001 configure the CommsModel (delay, drop rate, reorder window) so TaskH_COORD_RISK can run with comms impairments and produce stable results with seed_base. Results v0.2 can include an optional **coordination** block with **comm.msg_count**, **comm.p95_latency_ms**, **comm.drop_rate**; summarize-results and the coordination study Pareto report include these columns when present. See `tests/test_blackboard_replay_determinism.py` and `tests/test_view_staleness_effect.py`.

## Methods

### 0. kernel_centralized_edf (composed)

Kernel-composed method: CentralizedAllocator + EDFScheduler + TrivialRouter. Emits COORD_DECISION each step with allocation/schedule/route hashes and explain summaries. Same interface as other methods; use for ablation (e.g. swap router only and compare route_hash).

**Expected vulnerabilities**: Same as centralized_planner (R-SYS-001, R-COMMS-001, R-FLOW-002).

---

### 0b. kernel_whca (composed, WHCA* router)

Kernel-composed method: CentralizedAllocator + EDFScheduler + **WHCARouter**. Uses a reservation table over the zone graph and windowed cooperative A* (WHCA*) for collision-free moves over a finite horizon (default 15 steps). Deadlock-safe fallback: wait-in-place (NOOP). Restricted door edges (INV-ROUTE-002) are never planned without valid token. Metrics: `coordination.route` with `replan_rate`, `mean_plan_time_ms`, `deadlock_avoids`. Scale configs in `policy/coordination/scale_configs.v0.1.yaml` (e.g. corridor_heavy: 200 agents). Run: `labtrust run-benchmark --task TaskG_COORD_SCALE --coord-method kernel_whca --episodes 1 --seed 42 --out results.json`. Determinism: same seed yields identical paths and decision hashes.

**Routing invariants** (coordination-layer, see `routing/invariants.py`): **INV-ROUTE-001** no two agents occupy same (time, node) over planned horizon; **INV-ROUTE-002** restricted door edges require valid token or are never planned. Evaluated in tests and optionally in study runner.

---

### 0b2. kernel_scheduler_or / kernel_scheduler_or_whca (OR scheduling kernel)

Operations-research-grade baseline: **CentralizedAllocator** + **ORScheduler** (rolling-horizon) + **TrivialRouter** or **WHCARouter**. Policy: `policy/coordination/scheduler_or_policy.v0.1.yaml` (weights, horizon_steps, replan_cadence_steps, fairness_regularizer). Objective: weighted tardiness + throughput + violation penalties + coordination overhead. Priorities STAT/URGENT/ROUTINE, device capacity and colocation, zone and transport constraints; safety shields (RBAC/tokens) are enforced so the scheduler never proposes illegal START_RUN (no START_RUN for agents whose role disallows it or in restricted zone without token).

**Metrics**: `coordination.sched` (mean_plan_time_ms, replan_rate, deadlock_avoids), `coordination.alloc` (gini_work_distribution), `coordination.route` (when WHCA: replan_rate, deadlock_avoids). Deterministic and fast at scale.

**Complexity**: O(agents × work items) per step for allocation and schedule filtering; planning time reported in sched.mean_plan_time_ms.

**Failure modes**: Same as centralized (R-SYS-001 single point of failure, R-COMMS-001, R-FLOW-002); scheduler output always passes coordination contract (no illegal actions under strict RBAC/token mode). Official non-LLM coordination baseline for TaskG_COORD_SCALE and TaskH_COORD_RISK (`benchmarks/baseline_registry.v0.1.yaml`: kernel_scheduler_or_v0).

---

### 0c. kernel_auction_edf / kernel_auction_whca (market-based allocator)

Kernel-composed methods: **AuctionAllocator** (sealed-bid auction) + EDFScheduler + TrivialRouter or WHCARouter. Allocation is no longer heuristic-only: each agent bids based on distance-to-work (routing graph), queue load, role constraints, and congestion-aware price signals (zone congestion, device queue price). Auction runs with a strict bid budget (`max_bids` per step); deterministic stable ordering and seeded tie-breaks. RBAC and token constraints are respected (allocator cannot assign forbidden actions). Metrics: `coordination.alloc` with **gini_work_distribution**, **mean_bid**, **rebid_rate**, and optional **alloc_emits** (e.g. BID_ANOMALY_DETECTED).

**Bid anomaly detector**: When enabled (default), outlier low bids are flagged (emit BID_ANOMALY_DETECTED, reason_code BID_ANOMALY_SPOOF_SUSPECTED); the flagged agent is contained (bids ignored for K steps). **INJ-BID-SPOOF-001**: Compromised agent publishes artificially low bids (injection via `scale_config.injection_id`); detector mitigates by containment. Method-risk matrix: market allocator partially covers congestion (R-FLOW-002), vulnerable to bid spoof (R-DATA-001) unless detector enabled. TaskH smoke: run with `--coord-method kernel_auction_edf --injection INJ-BID-SPOOF-001`; results include `coordination.alloc`. See `tests/test_auction_respects_rbac.py`, `tests/test_bid_spoof_detection.py`.

---

### 1. centralized_planner

Single global planner builds a worklist and assigns agents to the next best action using greedy heuristics:

- Prioritizes STAT > URGENT > ROUTINE.
- Respects colocation (agent must be in same zone as device for START_RUN).
- Prefers shortest queue and device availability.
- **Compute budget**: Optional knob to limit assignments per step and simulate planner saturation at scale.

**Expected vulnerabilities** (risk IDs from `policy/risks/risk_registry.v0.1.yaml` and `policy/coordination/method_risk_matrix.v0.1.yaml`): R-SYS-001 (single point of failure, DoS), R-COMMS-001 (hub identity/spoofing), R-FLOW-002 (progress/deadlock under load).

---

### 2. hierarchical_hub_rr

Hub assigns tasks to cells (zones/sites); within each cell, local rapid-response handles exceptions (critical, QC fail, door breach).

- Message delay between hub and cells is modeled deterministically as a function of scale (e.g. steps delay).
- Local RR takes precedence over delayed hub assignments.

**Expected vulnerabilities**: [R-SYS-002](policy/risks/risk_registry.v0.1.yaml), [R-COMMS-002](policy/coordination/method_risk_matrix.v0.1.yaml) (message auth / poisoning), [R-FLOW-002](policy/risks/risk_registry.v0.1.yaml).

---

### 2b. hierarchical_hub_local (Hub + local controllers, handoff protocol)

Hub assigns work at macro-level to regions (deterministic partition of zones); each region has a LocalController (EDF + TrivialRouter). HandoffEvent protocol: hub-to-region assignment requires ACK within T steps; missing ACK triggers escalation. Metrics: coordination.hierarchy (cross_region_handoffs, handoff_fail_rate, escalations). At large N in TaskG with comms model active, can reduce comm.msg_count vs centralized. Registry: required_controls include handoff_ack_deadline. See hierarchical/, test_hierarchy_handoff_protocol.py, test_hierarchy_determinism.py.

---

### 3. market_auction (contract net)

Tasks announce; agents bid by estimated cost/time; auctioneer selects winners.

- Optional **collusion** toggle for risk injection (e.g. one agent biases bids).
- Deterministic given seed and observations.

**Expected vulnerabilities**: R-DATA-001 (untrusted payload in bids/awards), R-COMMS-002, R-TOOL-006.

---

### 4. gossip_consensus

Local load balancing: agents share queue head and local load; converge to a stable assignment using a fixed small K gossip rounds per step.

- Degrades gracefully under message loss (deterministic drop model).
- No central auctioneer; assignment by consensus within rounds.

**Expected vulnerabilities**: R-COMMS-002 (poisoning amplification), R-DATA-003, R-FLOW-002.

---

### 5. swarm_reactive

Purely local rules; zero global state.

- If near restricted door and alarm: close/exit (TICK or MOVE away).
- If device queue empty and specimens waiting: QUEUE_RUN (when colocated).
- If QC fail: rerun path (local heuristic).

**Expected vulnerabilities**: [R-TOOL-001](policy/risks/risk_registry.v0.1.yaml), [R-FLOW-001](policy/risks/risk_registry.v0.1.yaml), [R-SYS-001](policy/risks/risk_registry.v0.1.yaml).

---

### 6. marl_ppo

If Stable-Baselines3 (and gymnasium) is installed, reuses the existing PPO policy wrapper for evaluation. If not installed, a stub raises a clear error and the method is skipped in studies unless the `[marl]` extra is present.

**Expected vulnerabilities**: R-DATA-002, R-FLOW-002, R-TOOL-004.

---

### 7. llm_constrained

Reuses the existing `baselines/llm/agent.py` (LLMAgentWithShield) as a CoordinationMethod: one LLM agent instance, `propose_actions` calls `act(obs[agent_id], agent_id)` per agent. Uses the existing constrained decoder stack; logs LLM_DECISION (already present in the agent meta) into step outputs when available.

**Expected vulnerabilities**: R-TOOL-001, R-TOOL-005, R-CAP-001, R-DATA-001.

---

## Registry and factory

### 7b. llm_repair_over_kernel_whca (repair-over-kernel)

Base plan is produced by a deterministic kernel method (default: **kernel_whca**). The LLM is used only as a repairer/sanitizer when: (1) the shield rejects the kernel action set, (2) a security detector flags comms poisoning, inconsistent view, or spoofed identity, or (3) plan staleness exceeds policy limit (e.g. coordination.timing.p95_view_age_ms). Flow: kernel plan -> shield validate -> if blocked or flagged -> build deterministic repair input (scale_config snapshot, last accepted plan summary, blocked actions with reason codes, constraint summary, red-team flags) -> call LLM repair backend -> re-shield repaired plan -> execute or fallback to NOOP.

**Repair input** is canonicalized (stable key order, no timestamps) so that same logical input yields same JSON and same hash; determinism in llm_offline is preserved via a deterministic repair backend (seed + repair_input_hash). **Metrics**: optional `coordination.llm_repair` block in results v0.2: `repair_call_count`, `repair_success_rate`, `repair_fallback_noop_count`, `mean_repair_latency_ms` (null offline), `total_repair_tokens` (0 offline). Required controls: signed_actions, message_auth, shield_execute, repair_loop. Compatible injections: INJ-COMMS-POISON-001, INJ-ID-SPOOF-001, INJ-LLM-PROMPT-INJECT-COORD-001. TaskH with INJ-COMMS-POISON-001 or INJ-ID-SPOOF-001 runs produce sec metrics and nonzero repair calls when the runner sets repair triggers. Run: `labtrust run-benchmark --task TaskH_COORD_RISK --coord-method llm_repair_over_kernel_whca --injection INJ-COMMS-POISON-001 --episodes 1 --seed 42 --out results.json`.

---

- **Registry**: `policy/coordination/coordination_methods.v0.1.yaml` lists `method_id`, name, coordination_class, scaling_knobs, known_weaknesses (risk_id), required_controls, compatible_injections, default_params. Includes kernel-composed methods (e.g. kernel_centralized_edf, kernel_whca, kernel_auction_edf, kernel_auction_whca) and hierarchical_hub_local; **kernel_auction_whca_shielded** is the auction+WHCA method wrapped by the Simplex shield (see assurance/simplex.py); **llm_repair_over_kernel_whca** is repair-over-kernel (see above).
- **Factory**: `make_coordination_method(method_id, policy, repo_root=None, scale_config=None, **kwargs)` loads default_params from the registry and instantiates the corresponding method. For `llm_constrained`, `llm_agent` must be passed; for `marl_ppo`, a trained model path can be passed when SB3 is available.

## Usage

- **CLI**: `labtrust run-benchmark --task TaskG_COORD_SCALE --coord-method centralized_planner --episodes 1 --seed 42 --out results.json`
- **Runner**: For TaskG_COORD_SCALE and TaskH_COORD_RISK, when `--coord-method` is set, the benchmark uses the chosen coordination method to drive all agents; actions are converted to `(action_index, action_info)` and passed to `env.step()`. RBAC and signature rules are not bypassed; the env and engine enforce them as for scripted/LLM baselines.
