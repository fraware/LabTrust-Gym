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
| MAPF property-based test | Done | test_mapf_property_whca_collision_free: 30 graphs, 7 pairs per graph (210 total); WHCA collision-free via check_inv_route_001 and check_swap_collision. CBS/ECBS skipped until [mapf]. |
| MAPF backend equivalence | Blocked | On tiny graphs, CBS and WHCA both collision-free; CBS cost <= WHCA cost. **Blocked on [mapf] CBS backend.** Placeholder test in tests/test_mapf_property.py::test_mapf_cbs_equivalence skips until CBS is available. |
| Min-cost flow: brute-force vs MCF | Done | test_min_cost_flow_brute_force_vs_mcf: _brute_force_optimal_cost enumerates assignments (N,M<=6), asserts MCF cost equals optimum. |
| Min-cost flow: forbidden edges | Done | test_min_cost_flow_forbidden_edges: forbidden_edges (agent, (dev_id, work_id)) asserted never in MCF assignments. |
| Min-cost flow: Gini vs baseline | Done | test_min_cost_flow_gini_fairness: fairness_weight=0.2 yields Gini <= fairness_weight=0. |
| EDF: STAT preemption test | Done | test_edf_stat_preemption: STAT (slack 3) scheduled before ROUTINE (slack 20) when preemption_sla_threshold=5. |
| EDF: aging starvation test | Done | test_edf_aging_starvation: ROUTINE with work_wait_steps boosted scheduled first. |
| ORScheduler: infeasibility report | Done | Fallback explain includes or_cpsat_infeasible; test_orscheduler_cp_sat_infeasible_returns_fallback_with_reason (horizon=0, two tasks same agent). |
| ORScheduler: timeout test | Done | test_orscheduler_timeout_returns_fallback_no_hang and test_or_scheduler_time_budget_fallback: time_budget_ms respected, fallback used. |

---

## Phase 2 (Auction)

| Step | Status | Action |
|------|--------|--------|
| Bundle: bundle wins vs two bids | Done | test_bundle_wins_vs_two_bids_a1_near, test_bundle_wins_both_when_bundle_cheaper_than_split: bundle bid wins. |
| Learning-to-bid: training determinism | Done | MinimalRegressor with get_checksum(); test_learning_to_bid_training_determinism. |
| Learning-to-bid: calibration | Done | calibration_mae with MinimalRegressor; test_calibration_mae_decreases_with_more_data. |

---

## Phase 3 (Gossip / CRDT)

| Step | Status | Action |
|------|--------|--------|
| CRDT in gossip methods | Done | llm_gossip_summarizer: LWW for queue_head_by_device; gossip_consensus: PN-counter for zone_counts. Docstrings list CRDT per field. |
| Merge order independence test | Done | test_crdt_merge_order_independence: LWW, PN-counter, OR-set (A then B) == (B then A). |
| Byzantine: inject k reports | Done | test_byzantine_inject_k_trim_mean, test_byzantine_inject_k_graceful_degradation. |

---

## Phase 4 (Swarm)

| Step | Status | Action |
|------|--------|--------|
| Wire stability into swarm | Done | swarm_reactive uses inertia_term for zone choice; swarm_stigmergy_priority already uses congestion_penalty and pheromone_diffusion. |
| Oscillation test | Done | test_swarm_symmetric_corridor_no_infinite_pingpong: zone state simulated, ping-pong count bounded. |
| Herding test | Done | test_swarm_herding_congestion_reduces_pileup: congestion_penalty_scale>0, move_count >= 1. |

---

## Phase 5 (LLM)

| Step | Status | Action |
|------|--------|--------|
| 5.1–5.6 implementation | Done | Done (5.1–5.6): committee backend + tests, hierarchical confidence/assumptions + fallback tests, auction explainable bids + recompute + tests, gossip hash commitments + validation + tests, repair 3–10 candidates + validator + tests, detector probability/abstain/counterfactual + tool wiring + tests. See phase5_llm_upgrades.md for definition of done. |

---

## Definition of done (per method)

For any method to be marked "state of the art":

- Passes all 5 conformance contracts (skip removed).
- Method-specific property tests for core invariant.
- At least one scenario where it is strictly better than baseline (test asserts it).
- Produces METHOD_TRACE.jsonl (stable to diff).
- Documented compute/latency envelope and fallback (docstring or policy YAML).

Several methods now satisfy the full checklist (pass_budget, pass_evidence, strictly-better test, envelope). See [SOTA method roles and checklist](sota_method_roles_and_checklist.md). Regenerate the dashboard with `python scripts/refresh_sota_checklist.py` from repo root. Conformance skip/xfail and pass_budget/pass_evidence in conformance_config.yaml phase remaining upgrades.

**Checklist per method (maintainers):**

| Criterion | How to verify |
|-----------|----------------|
| All 5 contracts pass | No skip in [conformance_config.yaml](tests/coord_methods/conformance/conformance_config.yaml) for that method; run conformance matrix. |
| Property tests exist | Method-specific test file or test_* in tests/; core invariant covered. |
| Scenario strictly better than baseline | At least one test in [test_coord_strictly_better.py](../tests/test_coord_strictly_better.py) asserts method outperforms baseline on a defined scenario. |
| METHOD_TRACE emission and stability | Runner or test sets trace_path / trace_from_contract_record; same seed yields same trace_event_hash. |
| Compute/latency and fallback documented | Method docstring or policy YAML describes envelope and fallback strategy. |

**Methods meeting definition of done:** See [SOTA method roles and checklist](sota_method_roles_and_checklist.md) and `python scripts/refresh_sota_checklist.py` for the current table (pass_budget, pass_evidence, strictly_better_test, envelope per method_id).

---

## Suggested priority order

1. **Trace emission in runner** – Enables evidence contract and diff-stable artifacts; small change in runner/compose.
2. **Definition of done per method** – For each coordination method, run checklist above; remove skips where contracts pass; add property/scenario tests and docs; then add to "Methods meeting definition of done."
