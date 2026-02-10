# SOTA Coordination Methods Roadmap (state-of-the-art at scale)

This document provides a **taxonomy of coordination at scale**, a **method-to-risk mapping** aligned with the existing risk system (injections v0.2, reason codes, identity policy, memory policy), and a **roadmap of planned state-of-the-art methods** with explicit failure modes and stress injections. It is the single "go deep" plan that maps algorithms to LabTrust method types and risks.

---

## A) Taxonomy: kinds of coordination at scale

| Class | Description | LabTrust alignment |
|-------|-------------|--------------------|
| **Centralized planning** | Single authority solves MILP, MAPF, or scheduling over global state. Optimizes throughput, tardiness, or makespan under constraints. | `centralized`; kernel methods: `kernel_centralized_edf`, `kernel_scheduler_or`, `kernel_whca`. |
| **Hierarchical** | Manager/worker or hub-and-spoke: high-level assignments, local execution (EDF, greedy, WHCA). Reduces coupling and scales via delegation. | `hierarchical`; e.g. `hierarchical_hub_rr`, `hierarchical_hub_local`, `llm_hierarchical_allocator`. |
| **Market-based** | Auctions (sealed-bid, combinatorial) or contract nets. Price signals and bids drive allocation; congestion and fairness emerge from market clearing. | `market`; e.g. `market_auction`, `kernel_auction_edf`, `kernel_auction_whca`, `llm_auction_bidder`. |
| **Consensus / gossip** | Agreement on shared state via broadcast and merge (e.g. gossip, Paxos-like). Used for view synchronization and distributed summaries. | `decentralized`; e.g. `gossip_consensus`, `llm_gossip_summarizer`. |
| **Swarm / reactive** | Stigmergy, local rules, no central plan. Agents react to neighbors and environment; emergent order from simple rules. | `swarm`; e.g. `swarm_reactive`. |
| **Population-based learning / evolution** | Open-ended improvement via RL, evolution, or meta-learning. Policies or hyperparameters optimized over many episodes. | `learning`; e.g. `marl_ppo`. |
| **Experience sharing** | Cross-agent knowledge transfer: shared replay, demonstrations, or learned embeddings. Improves sample efficiency and generalization. | New class or under `learning`; see planned methods. |
| **Ripple / propagation protocols** | Local updates that spread globally (e.g. gradient-like propagation, constraint propagation). Bounded delay and eventual consistency. | New class or under `decentralized`; see planned methods. |
| **LLM-centric coordination** | Tool-constrained planners or bidders: LLM proposes high-level decisions (assignments, bids, summaries); deterministic shield and executor enforce safety. | `llm`; e.g. `llm_central_planner`, `llm_auction_bidder`, `llm_constrained`, `llm_local_decider_signed_bus`. |
| **Hybrid kernel + repair** | Deterministic kernel (allocation + scheduling + routing) with an LLM or heuristic repair loop on block/flag/stale. Minimizes LLM surface; kernel guarantees progress when repair fails. | `llm`; e.g. `llm_repair_over_kernel_whca`. |

---

## B) Method-to-risk mapping

The matrix below maps **risk themes** (collusion, poisoning, identity spoof, replay, observability gaps, degraded coordination under drop/latency) to **coordination classes** and to the existing **risk registry** (`policy/risks/risk_registry.v0.1.yaml`) and **injections** (`policy/coordination/injections.v0.2.yaml`). All method-risk coverage is recorded in `policy/coordination/method_risk_matrix.v0.1.yaml`; identity and memory are governed by `coordination_identity_policy.v0.1.yaml` and `memory_policy.v0.1.yaml`.

| Risk theme | Risk IDs (existing) | Relevant injections (v0.2) | Coordination classes most exposed |
|------------|---------------------|---------------------------|------------------------------------|
| **Collusion susceptibility** | R-SYS-002 | INJ-COLLUSION-001, INJ-BID-SPOOF-001, INJ-COLLUSION-MARKET-001, INJ-COORD-BID-SHILL-001 | market, experience_sharing |
| **Poisoning vulnerability** | R-COMMS-002, R-DATA-001, R-DATA-002, R-DATA-003 | INJ-COMMS-POISON-001, INJ-SLOW-POISON-001, INJ-MEMORY-POISON-001, INJ-MEMORY-POISON-COORD-001, INJ-CONSENSUS-POISON-001 | gossip, experience_sharing, llm |
| **Identity spoof** | R-COMMS-001 | INJ-ID-SPOOF-001 | All message-based; mitigated by signed_actions, message_auth |
| **Replay** | R-COMMS-001 | INJ-REPLAY-001, INJ-ID-REPLAY-COORD-001, INJ-COORD-PLAN-REPLAY-001 | All bus-based; mitigated by replay_protection, epoch binding |
| **Observability gaps** | R-FLOW-002, R-DATA-003 | INJ-PARTIAL-OBS-001, INJ-BLAME-SHIFT-001 | Emergent protocols, swarm, decentralized |
| **Degraded coordination under drop/latency** | R-SYS-001, R-FLOW-002 | INJ-TIMING-QUEUE-001, INJ-COMMS-FLOOD-LLM-001; CommsModel drop/delay | Centralized (single point), hierarchical (hub delay), consensus (convergence delay) |
| **LLM jailbreak / prompt injection** | R-CAP-001 | INJ-COORD-PROMPT-INJECT-001, INJ-LLM-PROMPT-INJECT-COORD-001 | llm |
| **Tool/API exploitation** | R-TOOL-006 | INJ-LLM-TOOL-ESCALATION-001 | llm, market (auction API) |

---

## C) Existing methods (summary)

Existing methods in `policy/coordination/coordination_methods.v0.1.yaml` already have `method_id`, `coordination_class`, `known_weaknesses` (risk_id list), and `compatible_injections`. See [Coordination methods](../coordination_methods.md) and [Coordination policy](../coordination_policy.md) for full registry and method-risk matrix.

---

## D) Planned SOTA methods (roadmap)

Each planned method below has: **method_id**, **coordination_class**, **what it optimizes**, **expected failure modes**, and **which injections should stress it**. These are candidates for future implementation and addition to the registry.

### D.1 Centralized planning

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `kernel_milp_planner` | centralized | Throughput and weighted tardiness via MILP over a rolling window; global optimum for the window. | Single point of failure (R-SYS-001); solver timeout under scale (R-FLOW-002); identity spoof if hub accepts spoofed obs (R-COMMS-001). | INJ-ID-SPOOF-001, INJ-COMMS-POISON-001; CommsModel drop to simulate hub starvation. |
| `kernel_mapf_cbs` | centralized | Conflict-free multi-agent paths (MAPF) via Conflict-Based Search; minimizes sum of path costs. | DoS via many agents (R-SYS-001); poisoning of start/goal (R-DATA-001); replay of stale plan (R-COMMS-001). | INJ-COORD-PLAN-REPLAY-001, INJ-MEMORY-POISON-COORD-001. |

### D.2 Hierarchical

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `hierarchical_region_auction` | hierarchical | Hub runs a lightweight auction per region; local controllers execute with EDF/WHCA. Balances global fairness and local latency. | Collusion across regions (R-SYS-002); hub-agent link poisoning (R-COMMS-002); handoff replay (R-COMMS-001). | INJ-COLLUSION-001, INJ-COMMS-POISON-001, INJ-ID-REPLAY-COORD-001. |

### D.3 Market-based

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `kernel_combinatorial_auction` | market | Welfare or makespan via combinatorial auction (packages of tasks); supports complementarities. | Bid spoof and shilling (R-DATA-001, R-SYS-002); auction API abuse (R-TOOL-006). | INJ-BID-SPOOF-001, INJ-COORD-BID-SHILL-001, INJ-COLLUSION-MARKET-001. |

### D.4 Consensus / gossip

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `consensus_paxos_lite` | decentralized | Agreement on a single global digest (e.g. queue heads, critical flags) for use by local policies; bounded rounds. | Poisoning of proposed value (R-COMMS-002, R-DATA-003); slow convergence under drop (R-FLOW-002). | INJ-CONSENSUS-POISON-001, INJ-COMMS-POISON-001; CommsModel drop_rate. |

### D.5 Swarm / reactive

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `swarm_stigmergy_priority` | swarm | Priority-weighted stigmergy: agents leave virtual pheromone by priority class; others follow gradients. No central plan. | Wrong tool selection under noisy pheromone (R-TOOL-001); poisoning of shared pheromone view (R-DATA-001); observability gaps (R-FLOW-002). | INJ-COMMS-POISON-001, INJ-PARTIAL-OBS-001. |

### D.6 Population-based learning / evolution

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `marl_qmix` | learning | Centralized critic, decentralized actors; QMix or similar for cooperative value decomposition. Sample-efficient coordination. | Reward/obs poisoning (R-DATA-002); progress risk under distribution shift (R-FLOW-002). | inj_poison_obs, inj_poison_reward (or INJ-* equivalents when defined). |
| `evolution_strategies_coord` | learning | Policy parameters evolved (ES) for coordination reward; population of agents evaluated per generation. | Data poisoning of fitness signal (R-DATA-002); collusion in fitness evaluation (R-SYS-002). | INJ-COLLUSION-001; poison on fitness reports. |

### D.7 Experience sharing

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `experience_replay_coord` | learning | Cross-agent replay buffer: agents share (s, a, r) or demonstrations; shared learner or distillation. Reduces sample complexity. | Poisoning of shared replay (R-DATA-002, R-DATA-001); collusion (agents feed fake good trajectories) (R-SYS-002). | INJ-COMMS-POISON-001, INJ-MEMORY-POISON-COORD-001; collusion injection on shared buffer. |
| `federated_coord_updates` | learning | Local policy updates with periodic aggregation (e.g. FedAvg); no raw experience leaves agents. | Byzantine updates (R-DATA-002); identity spoof of aggregated model (R-COMMS-001). | INJ-ID-SPOOF-001 (spoof contributor); poisoning of aggregated model. |

### D.8 Ripple / propagation protocols

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `ripple_constraint_prop` | decentralized | Local constraint propagation (e.g. capacity, deadlines) along zone/device graph; decisions use propagated bounds. | Poisoned bounds spread (R-COMMS-002, R-DATA-003); observability gaps if propagation drops (R-FLOW-002). | INJ-CONSENSUS-POISON-001, INJ-TIMING-QUEUE-001; CommsModel drop. |
| `ripple_priority_flood` | decentralized | Priority or urgency values flood from critical nodes; agents use local max to order work. | Blame shift and delayed attribution (INJ-BLAME-SHIFT-001); poisoning of priority (R-DATA-001). | INJ-BLAME-SHIFT-001, INJ-COMMS-POISON-001. |

### D.9 LLM-centric coordination

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `llm_multi_phase_planner` | llm | Multi-phase plan (allocate → schedule → route) with tool-calling; each phase constrained by schema and shield. | Jailbreak and prompt injection (R-CAP-001); misparameterization (R-TOOL-005); untrusted context (R-DATA-001). | INJ-COORD-PROMPT-INJECT-001, INJ-LLM-PROMPT-INJECT-COORD-001, INJ-LLM-TOOL-ESCALATION-001. |
| `llm_negotiation_mediator` | llm | LLM mediates multi-party negotiation (e.g. resource splits); outputs binding agreements validated by policy. | Collusion via manipulated context (R-SYS-002); mediator jailbreak (R-CAP-001). | INJ-COLLUSION-001, INJ-COORD-PROMPT-INJECT-001. |

### D.10 Hybrid kernel + repair

| method_id | coordination_class | What it optimizes | Expected failure modes | Injections to stress it |
|-----------|-------------------|-------------------|------------------------|--------------------------|
| `llm_repair_over_kernel_mapf` | llm | Kernel MAPF (e.g. CBS) for nominal paths; LLM repair when kernel blocks or flags conflict. Same pattern as existing llm_repair_over_kernel_whca. | Repair prompt injection (R-CAP-001); identity spoof on kernel input (R-COMMS-001); replay of stale repair (R-COMMS-001). | INJ-LLM-PROMPT-INJECT-COORD-001, INJ-ID-SPOOF-001, INJ-COORD-PLAN-REPLAY-001. |

---

## E) Consistency with existing policy

- **Injections**: All injection IDs referenced above exist in `policy/coordination/injections.v0.2.yaml` or are legacy (e.g. `inj_poison_obs`) documented in the study spec. New injections for experience sharing or propagation can be added under the same schema (strategy_type, success_definition, detection_definition, containment_definition).
- **Reason codes**: Containment and detection use existing reason codes (e.g. SIG_INVALID, RBAC_ACTION_DENY, PROMPT_INJECTION_DETECTED, BID_ANOMALY_SPOOF_SUSPECTED) from `policy/reason_codes/` and coordination-specific codes (e.g. REPLAY_DETECTED, SEC_INJ_LLM_DETECTOR_INVALID).
- **Identity policy**: `policy/coordination_identity_policy.v0.1.yaml` and SignedMessageBus enforce agent identity and replay protection; new message-based methods must use the same bus and key binding.
- **Memory policy**: `policy/memory_policy.v0.1.yaml` and memory validators apply to shared state and long-horizon digests; experience sharing and propagation methods must respect memory boundaries and integrity checks.

When a planned method is implemented, add it to `coordination_methods.v0.1.yaml` with `method_id`, `name`, `coordination_class`, `scaling_knobs`, `known_weaknesses`, `required_controls`, `compatible_injections`, and extend `method_risk_matrix.v0.1.yaml` with the relevant (method_id, risk_id) cells and coverage.
