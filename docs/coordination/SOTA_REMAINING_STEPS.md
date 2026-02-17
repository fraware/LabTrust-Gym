# SOTA Coordination Plan: Remaining Steps

This document lists gaps between the current implementation and the full plan so that work can be prioritized and tracked.

---

## Phase 0 (Conformance and scenarios)

| Step | Status | Action |
|------|--------|--------|
| Runner writes METHOD_TRACE.jsonl | Done (compose) | Composed kernel (compose.py) writes one trace event per step when `scale_config["trace_path"]` is set. Benchmark runner can set this to get METHOD_TRACE.jsonl for kernel methods. Non-kernel methods: runner can write via `trace_from_contract_record(method_id, t, actions)` after each propose_actions. |
| METHOD_TRACE emission | Done | **Where**: Kernel methods (kernel_whca, kernel_auction_whca, etc.): compose/router write when trace_path set. Non-kernel methods in pass_evidence: runner or test writes via trace_from_contract_record after propose_actions. **Stability**: Same seed and policy yield same trace_event_hash (evidence contract in test_conformance_contract_matrix and test_evidence.py). |
| Single conformance entrypoint | Done | Pytest `tests/coord_methods/conformance/test_conformance_contract_matrix.py` parametrizes over (method_id, contract). |
| Expose planned path for routing | Done | WHCARouter (kernel_components.py) exposes get_last_planned_path() when scale_config["expose_planned_path"] is True; compose and llm_repair_over_kernel_whca delegate to it. Returns (planned_nodes, planned_moves, restricted_edges, agent_has_token). Conformance safety_invariants contract runs for routing_method_ids (kernel_whca, kernel_auction_whca, kernel_auction_whca_shielded, llm_repair_over_kernel_whca) when expose_planned_path is set in scale_config. |

---

## Phase 1 (Kernel)

| Step | Status | Action |
|------|--------|--------|
| MAPF property-based test | Not done | Plan: "30 graphs + 200 start/goal pairs; assert collision-free for each backend." Add property-based test for WHCA (and for CBS/ECBS when [mapf] provides them). |
| MAPF backend equivalence | Not done | "On tiny graphs, CBS and WHCA both collision-free; CBS cost <= WHCA cost." Requires real CBS implementation in [mapf]. |
| Min-cost flow: brute-force vs MCF | Not done | Plan: "Small N (<=6) brute-force optimum vs min-cost flow." Add test comparing MCF result to brute-force optimum on tiny instances. |
| Min-cost flow: forbidden edges | Partial | Forbidden_edges exist in API; add test that RBAC-forbidden (agent, task) pairs are never selected. |
| Min-cost flow: Gini vs baseline | Not done | "Fairness regularizer -> Gini decreases vs baseline." Add test comparing Gini with fairness_weight=0 vs >0. |
| EDF: STAT preemption test | Partial | Preemption logic and SLA threshold exist; add explicit test "STAT arrives mid-episode -> preemption occurs" (e.g. two tasks, STAT with tight slack ordered first). |
| EDF: aging starvation test | Partial | work_wait_steps and aging_steps_per_boost exist; add test "one ROUTINE would starve -> aging eventually schedules it" (e.g. inject work_wait_steps and assert ROUTINE gets scheduled). |
| ORScheduler: infeasibility report | Not done | When CP-SAT is used and constraints are impossible, return valid fallback and document infeasibility (e.g. in explain or reason code). |
| ORScheduler: timeout test | Not done | When [or_solver] installed, test that time_budget_ms is respected (solver returns within budget or fallback). |

---

## Phase 2 (Auction)

| Step | Status | Action |
|------|--------|--------|
| Bundle: bundle wins vs two bids | Not done | Plan: "One agent near two tasks -> bundle bid wins vs two separate far bids." Add scenario or unit test with distance/cost that demonstrates bundle winning. |
| Learning-to-bid: training determinism | Not done | "Same seed/data -> same model checksum." Add minimal regressor or stub that has a checksum and test determinism. |
| Learning-to-bid: calibration | Not done | "Predicted vs observed error decreases over epochs." Requires experience buffer and calibration metric. |

---

## Phase 3 (Gossip / CRDT)

| Step | Status | Action |
|------|--------|--------|
| CRDT in gossip methods | Partial | crdt_merges.py provides LWW, PN-counter, OR-set; plan asks to use them in llm_gossip_summarizer and gossip_consensus for shared-view merge. Wire these merges into the methods. |
| Merge order independence test | Not done | Test that merging (A then B) vs (B then A) yields same result. |
| Byzantine: inject k reports | Not done | "Inject k adversarial reports; assert assignment quality degrades gracefully up to k." Add test that uses byzantine_aggregate and injects bad values. |

---

## Phase 4 (Swarm)

| Step | Status | Action |
|------|--------|--------|
| Wire stability into swarm | Not done | swarm_stability.py has inertia_term, congestion_penalty, pheromone_diffusion; swarm_stigmergy_priority.py has its own pheromone logic. Integrate stability helpers into swarm_stigmergy_priority / swarm_reactive (e.g. use congestion_penalty to reduce pile-ups). |
| Oscillation test | Not done | "Symmetric corridor -> no infinite ping-pong." Add scenario or test that asserts no infinite A/B oscillation. |
| Herding test | Not done | "Congestion penalty reduces pile-ups." Add test or scenario. |

---

## Phase 5 (LLM)

| Step | Status | Action |
|------|--------|--------|
| 5.1–5.6 implementation | Not done | phase5_llm_upgrades.md documents definition of done; the actual code changes (multi-role committee, intent_confidence, explainable bids, codec checks, repair candidate set, detector calibration) are not implemented. Each requires method-specific changes and tests. |

---

## Definition of done (per method)

For any method to be marked "state of the art":

- Passes all 5 conformance contracts (skip removed).
- Method-specific property tests for core invariant.
- At least one scenario where it is strictly better than baseline (test asserts it).
- Produces METHOD_TRACE.jsonl (stable to diff).
- Documented compute/latency envelope and fallback (docstring or policy YAML).

Currently no method has all of these; conformance skip/xfail and pass_budget/pass_evidence are used to phase upgrades.

---

## Suggested priority order

1. **Trace emission in runner** – Enables evidence contract and diff-stable artifacts; small change in runner/compose.
2. **Min-cost flow tests** – Forbidden edges, Gini vs baseline, brute-force comparison.
3. **EDF preemption/aging tests** – STAT preemption scenario, ROUTINE starvation + aging.
4. **CRDT wired into gossip** – Use LWW/PN/OR-set in gossip_consensus and llm_gossip_summarizer.
5. **Swarm stability integration** – Use inertia/congestion/pheromone helpers in swarm methods; add oscillation/herding tests.
6. **Phase 5 LLM upgrades** – Implement 5.1–5.6 per phase5_llm_upgrades.md.
