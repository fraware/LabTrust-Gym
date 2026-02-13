# Coordination method fidelity notes

For each implemented coordination method, this document states which algorithm is implemented, which invariants are checked, and where in the codebase they are enforced or tested. Used to satisfy the SOTA fidelity checklist (algorithmic and evaluation fidelity).

---

## kernel_whca

**Algorithm:** Windowed cooperative A* (WHCA*) over a zone-graph reservation table. CentralizedAllocator + EDFScheduler + WHCARouter. Reference: collision-free multi-agent pathfinding with a finite planning horizon; reservation table prevents two agents from occupying the same (time, node).

**Key invariants:**

- **INV-ROUTE-001:** No two agents occupy the same (time, node) over the planned horizon. Enforced by WHCARouter reservation table and path search that avoids reserved (t, node) slots.
- **INV-ROUTE-002:** Restricted door edges are never planned without a valid token. Router checks token/zone policy before adding restricted-door edges to the graph.

**Where checked:**

- Reservation consistency and collision freedom: `src/labtrust_gym/baselines/coordination/routing/` (WHCARouter, reservation table). Tests: `tests/test_coordination_kernel_determinism.py`, `tests/test_coordination_kernel_composition.py`; routing invariants in `routing/invariants.py` (evaluated in tests and optionally in study runner).

**Fidelity claim:** Implementation matches WHCA*-style reservation-based pathfinding; same seed yields identical paths and decision hashes.

---

## kernel_auction_edf / kernel_auction_whca (market_auction-style allocator)

**Algorithm:** Sealed-bid auction for work allocation; deterministic bid ordering and tie-breaks. AuctionAllocator computes bids from distance-to-work, queue load, role constraints, and congestion signals; winner selection by cost/score with seeded RNG.

**Key invariants:**

- **RBAC and tokens:** Allocator cannot assign work that would require an action disallowed by RBAC or missing token; bids and assignments respect role and token constraints.
- **Bid budget:** At most `max_bids` bids per step; deterministic stable ordering.

**Where checked:**

- Auction logic and RBAC: `src/labtrust_gym/baselines/coordination/kernel_components.py` (AuctionAllocator). Tests: `tests/test_auction_respects_rbac.py`, `tests/test_bid_spoof_detection.py`. Bid anomaly detector (BID_ANOMALY_DETECTED, containment) when INJ-BID-SPOOF-001 is used.

**Fidelity claim:** Allocation is by sealed-bid auction with deterministic tie-breaks; RBAC and token constraints are enforced before assignment.

---

## ripple_effect (ripple_constraint_prop-style)

**Algorithm:** Local constraint propagation along zone/device graph; agents use propagated bounds for decisions. Propagation follows a defined neighbor graph; no central planner.

**Key invariants:**

- **Neighbor graph:** Propagation follows edges defined in policy/layout; updates flow along graph only.
- **Signed bus / conflict resolution:** When used with a signed bus or blackboard, propagation and conflict resolution follow the documented protocol (see coordination_methods.md SOTA fidelity checklist).

**Where checked:**

- Propagation and neighbor graph: `src/labtrust_gym/baselines/coordination/ripple_effect.py`. Updates and seeding: checkpoints, get_learning_metadata; tests for propagation along edges and determinism.

**Fidelity claim:** Ripple protocol propagates via neighborhoods (neighbor graph); implementation matches the described propagation semantics.

---

## group_evolving_experience_sharing

**Algorithm:** Experience sharing that updates policy/params (e.g. routing_weights from summaries); evolution = selection + mutation + inheritance.

**Key invariants:**

- **Evolution loop:** select_top_k, mutate_genome, recombine_genomes as in evolution_loop.py; updates logged and seeded (mutation_log.jsonl, checkpoints).
- **Experience summaries:** routing_weights or other params updated from shared summaries; no raw experience leaves agents in federated-style variants.

**Where checked:**

- `src/labtrust_gym/baselines/coordination/group_evolving/` (evolution_loop.py, experience sharing). get_learning_metadata; determinism tests.

**Fidelity claim:** Evolution loop implements selection, mutation, and recombination; experience sharing changes policy/params from summaries as described.

---

## llm_repair_over_kernel_whca

**Algorithm:** Base plan from a deterministic kernel (default kernel_whca); LLM used only as repairer when shield blocks, security detector flags, or plan staleness exceeds limit. Repair input is canonicalized for determinism (offline backend).

**Key invariants:**

- **Repair trigger:** Repair is invoked only on shield block, security flag, or staleness; kernel plan is executed when valid.
- **No bypass:** Repaired plan is re-shielded; execution or fallback to NOOP only after validation.

**Where checked:**

- Repair flow and shield: LLM repair integration, shield_execute, repair_loop. Metrics: coordination.llm_repair (repair_call_count, repair_success_rate, repair_fallback_noop_count). Tests: coord_risk with INJ-COMMS-POISON-001 or INJ-ID-SPOOF-001.

**Fidelity claim:** Repair-over-kernel flow matches the documented trigger conditions and re-shield step; determinism preserved for offline repair backend via repair_input_hash and seed.

---

## consensus_paxos_lite

**Algorithm:** Leader-based agreement on a single global digest (e.g. device_id -> queue_head) in bounded rounds. Leader = agents[t % n]; leader proposes digest from queue_by_device; all agents use the digest for local actions (move toward device zones, START_RUN when colocated with head, QUEUE_RUN when at device with queue but no head).

**Key invariants:**

- **Bounded rounds:** max_rounds (default 2) limits consensus steps per env step.
- **Digest usage:** All agents act on the same digest once agreed; no central auctioneer.

**Where checked:**

- `src/labtrust_gym/baselines/coordination/methods/consensus_paxos_lite.py`. Uses extract_zone_and_device_ids, get_zone_from_obs, get_queue_by_device, queue_has_head, device_qc_pass, log_frozen, build_adjacency_set; local _bfs_one_step for movement.

**Fidelity claim:** Single global digest, bounded rounds; fits existing bus and identity; same seed yields deterministic digest and actions.

---

## swarm_stigmergy_priority

**Algorithm:** Priority-weighted stigmergy: pheromone per zone with decay; deposit on QUEUE_RUN/START_RUN. Agents follow gradient (move to adjacent zone with highest pheromone); if no gradient, fallback BFS toward device zones with work. Restricted zone: TICK when frozen.

**Key invariants:**

- **Pheromone decay:** Per-step decay (default 0.95); deposit on coordination actions.
- **Gradient follow:** Movement to max pheromone neighbor; BFS fallback when no gradient.

**Where checked:**

- `src/labtrust_gym/baselines/coordination/methods/swarm_stigmergy_priority.py`. Params: pheromone_decay, pheromone_deposit; _pheromone dict keyed by zone; restricted zone handled via log_frozen.

**Fidelity claim:** Stigmergy state and gradient follow as described; no central plan; reuses zones and device layout.

---

## Centralized and hierarchical methods

- **kernel_centralized_edf / centralized_planner:** Greedy allocation + EDF scheduling + trivial or WHCA routing; colocation and priority (STAT/URGENT/ROUTINE) as documented. Invariants: engine-level (RBAC, tokens, colocation) enforced in core_env; coordination layer does not bypass them.
- **hierarchical_hub_rr / hierarchical_hub_local:** Hub-to-cell assignment and local controllers; handoff protocol with ACK deadline. Invariants: handoff_ack_deadline, cross_region_handoffs; tests in test_hierarchy_handoff_protocol.py, test_hierarchy_determinism.py.

---

## Adding fidelity for a new method

When adding a new coordination method:

1. Add a subsection above: **method_id**, **Algorithm**, **Key invariants**, **Where checked**, **Fidelity claim**.
2. Add or extend tests that assert at least one invariant (e.g. propagation along edges, reservation consistency, auction rules).
3. Ensure the method is listed in `coordination_methods.v0.1.yaml` and `method_risk_matrix.v0.1.yaml` with correct known_weaknesses and compatible_injections.

See also: [SOTA fidelity checklist](../coordination_methods.md#sota-fidelity-checklist), [SOTA_ROADMAP.md](../SOTA_ROADMAP.md) section 3.
