# How Coordination Methods Work (Detailed)

This document describes in detail how each coordination method in LabTrust-Gym works: data flow, algorithms, invariants, and design choices. All methods implement the same `CoordinationMethod` interface (`reset`, `propose_actions`) and produce per-agent `action_dict` (action_index, optional action_type, args, reason_code). The registry is in `policy/coordination/coordination_methods.v0.1.yaml`; LLM-based methods are marked with `llm_based: true` and are the ones used for comparing coordination strategies on the same baseline.

---

## 1. Kernel-composed methods (allocation, scheduling, routing)

These methods are **composed** from three pluggable components. A **KernelContext** is built from `obs`, `infos`, `t`, policy, and scale_config; the pipeline is **Allocator -> Scheduler -> Router**, each deterministic and testable in isolation.

### 1.1 kernel_centralized_edf

- **Allocator: CentralizedAllocator**  
  Builds a global worklist from all agents' observations: for each agent, for each device with a queue head, if the agent is colocated with the device zone, the (device_id, work_id, zone_id, priority) is added. Priority: STAT=2, URGENT=1, ROUTINE=0. Worklist is sorted by (-priority, device_id, work_id). Assignment is greedy: for each work item in order, the first colocated agent not yet assigned gets it, up to a **compute_budget** (default agents × 2). Optional **fairness**: when True, among colocated agents the one with the fewest current assignments is chosen first (improves Gini work distribution). Output: `AllocationDecision(assignments, explain)`.

- **Scheduler: EDFScheduler**  
  For each (agent_id, work_id, device_id, priority) in the allocation, it assigns a **deadline** = current step `t` + slack. Slack is criticality-aware: `criticality_slack_steps` can map priority to different slacks (e.g. STAT=10, ROUTINE=20), else a single `deadline_slack_steps` is used. Per-agent work is ordered by (deadline, -priority, work_id). Output: `ScheduleDecision(per_agent: list of (agent_id, [(work_id, deadline, prio), ...])`.

- **Router: TrivialRouter**  
  For each agent: if the first item in its schedule is colocated (agent zone == device zone), emit START_RUN(device_id, work_id); else compute **next zone** toward the device zone via BFS on the zone graph (sorted neighbors for determinism), emit MOVE(from_zone, to_zone). Frozen agents get NOOP. Output: `RouteDecision(per_agent: (agent_id, action_type, args))`.

**State-of-the-art aspects:** Clear separation of allocation (who does what), scheduling (when / in what order), and routing (how to get there). Criticality-aware slack supports STAT vs ROUTINE SLA. Fairness option improves load balance.

---

### 1.2 kernel_whca

Same **CentralizedAllocator** and **EDFScheduler** as kernel_centralized_edf. The difference is the **Router: WHCARouter** (Windowed Cooperative A*).

- **Reservation table:** A table (time_step, zone_id) -> agent_id records which agent has reserved which zone at which time over a **horizon** (default 15, configurable via scale_config.whca_horizon).

- **WHCA* per agent:** For each agent, A* search runs in (time, zone) space: from (t0, current_zone) toward (goal_zone), with edge cost 1 per time step. A (time+1, neighbor_zone) is forbidden if already reserved by another agent. **INV-ROUTE-001**: no two agents occupy the same (time, node) in the plan. **INV-ROUTE-002**: restricted door edges are never used unless the agent has the required token (`has_restricted_token`). **INV-ROUTE-SWAP** (swap-collision invariant): no A→B and B→A at same time; check is in `routing/invariants.py` and applied by the simplex shield when used. Tie-breaking uses a seeded RNG for deterministic but varied neighbor order. If no path exists within the horizon, **deadlock-safe fallback**: wait in place (same zone at t+1), which is recorded for metrics.

- **Output:** First step of each agent's path is converted to MOVE or START_RUN (when already at device zone). Metrics: `replan_rate`, `deadlock_avoids`, `mean_plan_time_ms`.

**State-of-the-art aspects:** Collision-free multi-agent path planning without external MAPF libraries; horizon limits computation and allows replanning; wait-in-place avoids livelock; RBAC/token constraints are respected at the routing layer.

#### MAPF backend adapter contract

The routing layer uses a **router** abstraction that, given a graph, agent positions, goals, reservation table, and horizon, returns per-agent paths (or next move). **WHCARouter** implements this contract and is always available. **CBS, ECBS, LNS, RHCR** are optional backends that require the `[mapf]` extra; when `[mapf]` is not installed, `make_router("cbs")` (and the others) fall back to WHCARouter. The adapter contract:

- **Input:** Graph (zones, edges, restricted edges), current (time, zone) per agent, goal zone per agent, horizon, reservation table, RNG for tie-breaks, optional token/restricted-edge info.
- **Output:** Per-agent path as list of (t, zone), or first step only; must satisfy INV-ROUTE-001 (no same (t, zone) for two agents) and INV-ROUTE-002 (no restricted edge without token). Cost (e.g. sum of path lengths or makespan) can be used for equivalence: CBS optimality implies CBS cost <= WHCA cost on the same instance.

CBS/ECBS/LNS/RHCR are **placeholders** until a [mapf] dependency is chosen and a minimal adapter is implemented. The conformance config skips CBS; the equivalence test (`test_mapf_cbs_equivalence`) remains skipped until a CBS backend is available. See `src/labtrust_gym/baselines/coordination/routing/mapf_backends.py` and [State of the art and limits](../reference/state_of_the_art_and_limits.md).

---

### 1.3 kernel_scheduler_or / kernel_scheduler_or_whca

- **Allocator:** Same CentralizedAllocator.

- **Scheduler: ORScheduler**  
  Rolling-horizon optimization over H steps. Objective: weighted sum of **tardiness**, **throughput**, **violation_penalty**, and **coordination_overhead**; optional **fairness_regularizer**. Only (agent, device) pairs that pass **RBAC and token checks** (e.g. agent can START_RUN at that device zone) are considered; the scheduler never proposes illegal START_RUN. Policy is loaded from `scheduler_or_policy.v0.1.yaml` (horizon_steps, replan_cadence_steps, weights). Output: ScheduleDecision compatible with the kernel contract.

- **Router:** TrivialRouter (kernel_scheduler_or) or WHCARouter (kernel_scheduler_or_whca).

**State-of-the-art aspects:** Operations-research-grade scheduling with explicit objective and constraints; RBAC/token safety is enforced inside the scheduler so the coordination layer never emits disallowed actions.

---

### 1.4 kernel_auction_edf / kernel_auction_whca / kernel_auction_whca_shielded

- **Allocator: AuctionAllocator**  
  **Work items** are built from queue heads (device_id, work_id, zone_id, priority). Each agent **bids** for items it can serve (colocated or reachable; RBAC/token can forbid). **Bid formula:** distance-to-work (BFS path length) × 10 + queue_load × 2 + zone_congestion + device_queue_price - priority×5 + fairness_weight × current_assignment_count. Lower cost wins. **Price signals** (zone_congestion, device_queue_price) are derived from observations for congestion-aware pricing. **BID_FORBIDDEN** is returned when the agent cannot legally perform the work (e.g. restricted zone without token). Auction clears with a **max_bids** (compute budget); deterministic ordering and seeded tie-breaks. **Bid anomaly detector:** outlier low bids can be flagged (BID_ANOMALY_DETECTED); the flagged agent's bids are ignored for K steps (containment). Metrics: gini_work_distribution, mean_bid, rebid_rate.

- **Scheduler / Router:** EDFScheduler + TrivialRouter (kernel_auction_edf) or WHCARouter (kernel_auction_whca). **kernel_auction_whca_shielded** wraps the composed method in a Simplex-style shield: if the shield rejects the plan, a safe fallback is used and last_shield_emits are recorded.

**State-of-the-art aspects:** Market-based allocation with congestion and fairness; strict RBAC/token handling; bid validation and anomaly detection for security (e.g. INJ-BID-SPOOF-001).

---

## 2. Deterministic baseline methods (non-LLM)

These are scripted methods used as baselines or building blocks; they do not use an LLM.

### 2.1 centralized_planner

Single global worklist: from all agents' obs, build (priority, device_id, work_id, zone_id) for colocated queue heads; sort by (-priority, device_id, work_id). Greedy assignment: for each work item, assign to the first colocated agent not yet assigned, up to compute_budget. Then for each agent without START_RUN: BFS toward a zone that has work (or default zone); emit MOVE or NOOP. Optional TICK for door_restricted_open. Deterministic given seed and obs.

**State-of-the-art aspects:** Minimal dependency (no kernel composition); same priority/colocation logic as CentralizedAllocator; used as baseline for comparison with LLM central planner.

---

### 2.2 hierarchical_hub_rr

**Hub** maintains assignments (agent -> (work_id, device_id, zone_id)) with an **assignment_step** (when the assignment was issued). **Message delay** is modeled: num_agents and num_sites determine a base delay (e.g. 2 + (num_agents//10) + max(0, num_sites-1)) plus small random; assignments are "in flight" for that many steps. **Rapid response (RR):** Cells can act locally on exceptions (e.g. door restricted, QC fail, frozen zone): TICK, MOVE away, or local reroute. When an assignment is "delivered" (t >= assignment_step + delay), the agent executes START_RUN or MOVE toward the device zone. Deterministic given seed and obs.

**State-of-the-art aspects:** Hierarchical control with explicit message delay; local exception handling without waiting for hub; suitable for multi-site and scale.

---

### 2.3 hierarchical_hub_local

Hub assigns work; **local controllers** per region use EDF and per-region routing (ack_deadline_steps, sla_horizon). Handoff and region partition are defined in the hierarchical module (region_partition, handoff). Used for larger scales with regional autonomy.

---

### 2.4 market_auction

**Contract net:** Tasks are announced (all queue heads with zone and priority). Each colocated agent **bids** with an **estimated cost**: BFS path length from agent zone to task zone plus small tie-break (deterministic given rng). Optional **collusion** toggle (e.g. first agent artificially lowers bid) for risk injection. **Auctioneer** selects the lowest bid per task; winner gets START_RUN. Losers and unassigned agents get MOVE toward a zone with work or NOOP. Deterministic given seed and obs.

**State-of-the-art aspects:** Decentralized task allocation via auction; collusion flag supports security evaluation (e.g. INJ-COLLUSION-MARKET-001).

---

### 2.5 gossip_consensus

**K rounds of gossip** per step. Each agent has local state (queue heads, load). In each round, agents exchange messages (with deterministic **message loss** ~10% modeled for scale). **Aggregation:** Load from self and peers is aggregated by mode: sum (default), median, or trim_mean (Byzantine resilience). After K rounds, assignment is by **consensus**: e.g. assign work to the agent with lowest aggregated load in the zone. Then MOVE/START_RUN/NOOP as in centralized. Deterministic given seed and obs.

**State-of-the-art aspects:** No central planner; median/trim_mean reduce impact of faulty or Byzantine reports; bounded rounds for latency.

---

### 2.6 ripple_effect

**Local intent:** Each agent computes one intent: preferred (device_id, work_id, priority) if colocated with a queue head, else (zone_id for MOVE). Intents are **signed** (Ed25519) and published on **SignedMessageBus** with message type `ripple_intent`. **Neighbor graph:** Agents in the same zone or adjacent zones (from zone topology) are neighbors. Messages are broadcast to neighbors; **signature verification** and **epoch binding** reject invalid or replayed messages. **Conflict resolution:** Without a central planner, when two agents claim the same (device, work), deterministic tie-break (e.g. agent_id order) chooses one winner; the other gets NOOP or MOVE. Metrics: invalid_sig_count, replay_drop_count, spoof_attempt_count.

**State-of-the-art aspects:** Fully decentralized; signed bus and epoch binding for authenticity and replay protection; neighbor propagation limits blast radius; evaluable under INJ-ID-SPOOF-001, INJ-COMMS-POISON-001.

---

### 2.7 swarm_reactive

**Purely local rules;** no global state or messaging. If near restricted door and alarm -> TICK or MOVE away. If device queue has work and agent is colocated -> START_RUN or QUEUE_RUN when applicable. If qc_fail -> local rerun heuristic. BFS for movement. Deterministic given obs.

**State-of-the-art aspects:** Zero communication; useful as baseline for "no coordination" and for resilience under comms failure.

---

### 2.8 consensus_paxos_lite

**Bounded-round consensus** on a single **global digest** (e.g. device_id -> queue_head). **Leader** (deterministic from step and seed) proposes a digest; all agents adopt it. Local policies then use the agreed digest to choose actions (which device has which head). Max_rounds (default 2) caps latency. Deterministic given seed and obs.

**State-of-the-art aspects:** Single agreed view for decentralized decision; leader-based proposal reduces rounds; suitable for comms-poison evaluation (agreed view can be corrupted by injection).

---

### 2.9 swarm_stigmergy_priority

**Pheromone per zone:** Each zone has a pheromone level. When an agent performs QUEUE_RUN or START_RUN, it **deposits** pheromone in its current zone (weighted by priority: STAT_WEIGHT, URGENT_WEIGHT). Each step, pheromone **decays** (pheromone_decay, e.g. 0.95). Agents **follow the gradient**: when not doing work, move toward an adjacent zone with higher pheromone (priority-weighted). No central plan. Deterministic given seed and obs.

**State-of-the-art aspects:** Stigmergy (indirect coordination via environment); priority weighting aligns with SLA; decay avoids stale trails.

---

### 2.10 group_evolving_experience_sharing / group_evolving_study

**Experience buffer:** Episodes produce (state, action, outcome) summaries. **Sharing protocol:** Agents share compact summaries (build_experience_message, summaries_to_routing_weights). **Routing weights** per zone are derived from shared experience and used in a **greedy worklist + MOVE** kernel: worklist sorted by (priority, routing_weight, device_id, work_id); assignment and movement use these weights so high-utility zones are preferred. **Variant A (Experience Sharing Deterministic):** Fixed sharing interval and summary size; deterministic track. **Variant B (Group-Evolving Study):** **Evolution loop:** population of genomes (e.g. routing weights, strategy params), fitness_from_metrics, select_top_k, recombine_genomes, mutate_genome; checkpoints saved for reproducibility. Episodes per generation and top_k configurable.

**State-of-the-art aspects:** Learning from experience without a central LLM; evolution over populations for strategy search; deterministic track for CI, study track for research.

---

## 3. LLM-based coordination methods

These methods use an LLM (or deterministic backend that mimics the same interface) to produce coordination decisions. They are the ones compared as "coordination methods" on the same baseline.

### 3.1 llm_central_planner

- **State digest:** `build_state_digest(obs, infos, t, policy)` produces a **bounded, non-sensitive** digest: per_agent (agent_id, zone, task, last_action, local_queue_len), per_device (device_id, state, queue_head, utilization), per_specimen (stage, priority, SLA remaining; capped counts), comms_stats. Caps: MAX_AGENTS_DIGEST, MAX_DEVICES_DIGEST, MAX_SPECIMENS_DIGEST so token usage is controlled.

- **Proposal backend:** The backend (deterministic or live) receives (state_digest, allowed_actions, step_id, method_id) and returns a **CoordinationProposal**: proposal_id, step_id, method_id, per_agent (list of {agent_id, action_type, args, reason_code}), comms, meta (latency_ms, tokens_in, tokens_out, backend_id, model_id). Live backends use structured output constrained to the coordination_proposal schema.

- **Validation:** `validate_proposal(proposal, allowed_actions, strict_reason_codes)` checks schema and that every action_type is in allowed_actions. If **shielded** defense_profile, reason codes are strictly validated. Invalid proposal -> all agents NOOP.

- **Repair loop (runner):** If the shield blocks some actions, the runner can send a RepairRequest (blocked_reason_codes, state_digest) back; the coordinator may retry up to **max_repairs**. After cap, the last outcome is used.

- **Conversion:** Valid proposal per_agent is converted to action_dict (action_index, action_type, args, reason_code) via ACTION_TYPE_TO_INDEX. Runner executes; shield applies RBAC and signatures.

**State-of-the-art aspects:** Single global digest keeps context bounded and non-sensitive; schema validation and repair loop improve robustness; metrics (proposal_valid_rate, blocked_rate, repair_rate, tokens, latency) support comparison and cost attribution.

---

### 3.2 llm_hierarchical_allocator

- **Allocator backend** produces a **CoordinationProposal** where each per_agent entry has **action_type SET_INTENT** and **args {job_id, priority_weight}**. The LLM (or deterministic backend) does **not** output concrete MOVE/START_RUN; it outputs high-level assignments (agent -> job_id). **job_id** = "device_id:work_id" for a queue head.

- **Local controller:** `intent_to_actions(obs, assignments, zone_ids, device_ids, device_zone, strategy)` translates SET_INTENT into concrete actions. **Strategies:** greedy, edf, whca. For each agent with a job_id, the controller checks colocation; if colocated, START_RUN(device_id, work_id); else BFS MOVE toward device zone. EDF orders by deadline; WHCA uses the same reservation-based path planning as the kernel. The **shield** applies to the final concrete actions (RBAC, signatures), so the LLM cannot directly issue privileged ops.

**State-of-the-art aspects:** Reduces LLM authority to high-level intent; local controller is deterministic and testable; supports multiple local strategies (greedy, EDF, WHCA) for ablation.

---

### 3.3 llm_auction_bidder

- **Work items** are built from state (queue heads with device_id, work_id, zone_id, priority). The **bid backend** (LLM or deterministic) receives state_digest and produces a **market** list: each entry has agent_id, **bundle** (device_id, work_id or bundle_id), **bid** (value, units, constraints). **Strict bid validation:** validate_bid(value, units, constraints) and schema checks; invalid bids are dropped with errors.

- **Auction clear:** `clear_auction(work_items, typed_bids)` matches bids to work items; **lowest cost wins** per item. Assignments (agent_id, device_id, work_id, priority) are produced.

- **Deterministic dispatcher:** Assignments are converted to action_dict: each assigned agent gets START_RUN; others get MOVE toward a zone with work or NOOP (BFS). Metrics: bid_skew, gini_work_distribution, collusion_suspected_proxy. Evaluated under INJ-COLLUSION-001, INJ-BID-SPOOF-001, INJ-COMMS-POISON-001.

**State-of-the-art aspects:** LLM only proposes bids; clearing and execution are deterministic and auditable; typed bids and validation limit prompt injection and malformed output.

---

### 3.4 llm_gossip_summarizer

- **Per-agent summary:** Each agent builds a **local summary** (agent_id, step_id, zone_id, queue_summary, task) from its obs; queue_summary is a bounded list of {device_id, queue_len, queue_head}. Summary is **signed** and published on **SignedMessageBus** with message type `gossip_summary`. **Schema validation:** Message payload is validated against coordination_message schema; max payload size (e.g. 4096 bytes). **Poison heuristic:** Suspicious substrings or abnormal length can set COORD_POISON_SUSPECTED; such messages are dropped and counted.

- **Consensus:** Accepted messages are merged (deterministic merge) into a **shared view**. From the shared view, a **deterministic consensus** policy chooses assignments (e.g. which agent serves which work). Then MOVE/START_RUN/NOOP as in other methods. Metrics: invalid_sig_count, replay_drop_count, invalid_msg_rate, spoof_attempt_count.

**State-of-the-art aspects:** Distributed summarization with signed, typed messages; schema and size limits; poison detection; deterministic consensus so LLM affects only the content of summaries, not the final action selection.

---

### 3.5 llm_repair_over_kernel_whca

- **Base plan:** A **kernel** (CentralizedAllocator + EDFScheduler + WHCARouter) produces a full route (RouteDecision) each step. The **shield** (validate_plan) checks the plan; if it **blocks** some actions (e.g. RBAC, signature, or security/staleness flags), the blocked actions and **repair_input** (blocked_actions, constraint_summary, state digest) are built.

- **Repair backend:** **DeterministicRepairBackend** (for llm_offline): same repair_input + seed -> same repaired plan (e.g. all NOOP or TICK). **LiveRepairBackend:** LLM receives a prompt with repair_input, allowed_actions, agent_ids; returns a JSON array of {agent_id, action_type, args}. Parsed and validated; on parse/API error, fallback is all NOOP.

- **Execute:** Repaired per_agent list is converted to RouteDecision and then to action_dict. So the **default** is the kernel plan; LLM is only invoked when the kernel plan is blocked or flagged, reducing cost and keeping behavior predictable when the kernel is valid.

**State-of-the-art aspects:** Kernel-first ensures a safe baseline; LLM is used only for repair, with bounded prompt and fallback; deterministic backend supports offline verification.

---

### 3.6 llm_local_decider_signed_bus

- **Local view:** For each agent, a **bounded local view** (agent_id, step_id, zone_id, queue_summary) is built from obs; MAX_LOCAL_VIEW_BYTES caps size. No global state.

- **ActionProposal:** Each agent's **backend** (LLM or deterministic) produces an **ActionProposal** (action_type, args, reason_code, confidence, safety_notes). Proposals are **signed** and published on **SignedMessageBus** with message type `action_proposal`. **Signature and epoch gating:** Bus rejects invalid signature or replay (nonce already seen); spoof attempts (signature verifies with wrong sender) are counted.

- **Reconciliation:** Accepted proposals are passed to a **deterministic reconciler**: for START_RUN, if two agents claim the same (device_id, work_id), one winner (e.g. first in sorted agent order), the other overridden to NOOP. **conflict_rate** = overridden_count / total_proposals. Final action set is executed; shield applies RBAC and signatures.

**State-of-the-art aspects:** Strictly local view per agent; signed bus and reconciler give authenticity and conflict resolution without a central planner; metrics (invalid_sig_count, replay_drop_count, spoof_attempt_count, conflict_rate) support security evaluation.

---

### 3.7 llm_constrained

**Wraps** the existing **LLMAgentWithShield** (baselines/llm/agent) as a CoordinationMethod. For each agent, `propose_actions` calls `llm_agent.act(obs[agent_id], agent_id)` and maps the return (action_index, action_info, meta) to action_dict. So each agent is an independent LLM agent with the same shield and allowed-actions payload; no cross-agent coordination protocol. Used as baseline "LLM per agent, no coordination method".

**State-of-the-art aspects:** Reuses the same LLM agent and shield contract as the rest of the repo; clarifies the difference between "LLM agent" and "LLM coordination method".

---

### 3.8 llm_detector_throttle_advisor

**Wrapper** around another coordination method (e.g. kernel_auction_whca_shielded). A **detector backend** (deterministic or LLM) reads a **compact event stream summary** and **comms stats**, and outputs **DetectResult** (is_attack_suspected, suspected_risk_id, suspect_agent_ids) and **RecommendResult** (enforcement_action: throttle | freeze_zone | kill_switch | none, scope, rationale_short). Only **policy-allowed** enforcement actions are applied; invalid recommendations become NOOP with reason code RC_DETECTOR_INVALID_RECOMMENDATION. Emits LLM_DETECTOR_DECISION for audit. So the underlying method runs as usual; the detector can throttle or freeze in response to suspected attacks.

**State-of-the-art aspects:** Separation of "coordination" and "detection/containment"; policy-driven allowed actions; latency-bound detector (e.g. detector_latency_bound_steps) for real-time use.

---

### 3.9 Defended variants (shielded, safe_fallback)

- **llm_central_planner_shielded**, **llm_hierarchical_allocator_shielded**, **llm_auction_bidder_shielded:** Same as base method but with **defense_profile: shielded**: stricter reason-code validation; on reject, safe fallback (e.g. NOOP).

- **llm_*_with_safe_fallback:** **defense_profile: safe_fallback**: on backend exception or timeout, return all NOOP instead of raising. Used for resilience under API failure.

These variants are **composition over base methods** for matrix ranking and deployable stacks.

---

## 4. MARL and other learning methods

### 4.1 marl_ppo

Shared policy with **agent_id in observation**; PPO training produces a policy that maps (obs, agent_id) to action. Coordination emerges from training rather than from an explicit protocol. Deterministic track uses a fixed checkpoint; study track can update and record checkpoint_sha, update_count, buffer_size in metadata.coordination.learning. Not used as a coordination method for comparison in the LLM-based sense; listed in registry for completeness.

---

## 5. Summary table

| Method | Class | Allocation | Scheduling / routing | LLM role |
|--------|--------|------------|----------------------|----------|
| kernel_centralized_edf | centralized | CentralizedAllocator | EDF + TrivialRouter | None |
| kernel_whca | centralized | CentralizedAllocator | EDF + WHCARouter | None |
| kernel_scheduler_or(_whca) | centralized | CentralizedAllocator | ORScheduler + Trivial/WHCA | None |
| kernel_auction_edf/whca | market | AuctionAllocator | EDF + Trivial/WHCA | None |
| centralized_planner | centralized | Greedy worklist | BFS move / START_RUN | None |
| hierarchical_hub_rr/local | hierarchical | Hub + delay | Local RR or EDF/region | None |
| market_auction | market | Contract net bids | Lowest bid wins, BFS | None |
| gossip_consensus | decentralized | K-round gossip + consensus | BFS | None |
| ripple_effect | decentralized | Local intent + signed bus | Reconciler, BFS | None |
| swarm_reactive / swarm_stigmergy | swarm | Local rules / pheromone | BFS / gradient | None |
| consensus_paxos_lite | decentralized | Leader digest consensus | Local policy | None |
| group_evolving_* | decentralized | Experience weights | Greedy + MOVE | None |
| llm_central_planner | llm | State digest -> proposal | Proposal -> actions | Global proposal |
| llm_hierarchical_allocator | llm | Backend -> SET_INTENT | Local controller (greedy/edf/whca) | Assignments only |
| llm_auction_bidder | llm | Backend -> typed bids | clear_auction + dispatcher | Bids only |
| llm_gossip_summarizer | llm | Backend -> signed summary | Deterministic consensus | Summary content |
| llm_repair_over_kernel_whca | llm | Kernel plan | Repair when blocked | Repair only |
| llm_local_decider_signed_bus | llm | Per-agent proposal | Reconciler + shield | Per-agent proposal |
| llm_constrained | llm | N/A | Per-agent act() | Per-agent, no protocol |
| llm_detector_throttle_advisor | llm | Wrapper | Underlying method | Detect + recommend |

---

## See also

- [Coordination methods](coordination_methods.md) — Registry, interface, kernel composition, blackboard.
- [LLM Coordination Protocol](../benchmarks/llm_coordination_protocol.md) — Pipeline modes, proposal schema, shield, repair loop, security evaluation.
- [Coordination method contract](coordination_method_contract.md) — Schema and step contract.
- [Fidelity notes](fidelity_notes.md) — Algorithm and invariant fidelity per method.
