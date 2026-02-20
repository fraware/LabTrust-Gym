# Phase 5: LLM Method Upgrades (Definition of Done)

Per-method upgrade requirements from the SOTA coordination plan. Each method must pass the conformance suite and meet the following before being marked state-of-the-art.

## Implementation status

5.1–5.6 are implemented in code. Summary:

| Item | Implemented | Key code / tests |
|------|-------------|------------------|
| 5.1 llm_central_planner | Yes | DeterministicCommitteeBackend, _merge_committee_outputs; tests: test_llm_central_planner_committee_golden_trace, test_llm_central_planner_committee_corrupt_allocator_rejected (test_coordination_llm_sota_contracts.py). |
| 5.2 llm_hierarchical_allocator | Yes | intent_confidence, assumptions, risk_flags; _check_assumptions_match, confidence_threshold fallback; tests: test_hierarchical_low_confidence_fallback, test_hierarchical_assumption_mismatch_reject (test_coord_llm_hierarchical_allocator_smoke.py). |
| 5.3 llm_auction_bidder | Yes | TypedBid decomposition, _reject_inconsistent_bids; tests: test_auction_bid_inconsistent_rejected, test_auction_bid_adversarial_digest_schema_valid (test_coord_llm_auction_bidder_smoke.py). |
| 5.4 llm_gossip_summarizer | Yes | _compute_hash_commitment, _verify_hash_commitment; tests: test_gossip_hash_commitment_poisoned_rejected (test_coord_llm_gossip_summarizer_smoke.py). |
| 5.5 llm_repair_over_kernel_whca | Yes | DeterministicRepairBackend returns 3–10 candidates; _score_repair_candidate; tests: test_llm_repair_multi_candidate_validator_selects_first_valid, test_llm_repair_deterministic_backend_same_chosen_repair (test_llm_repair_over_kernel_whca.py). |
| 5.6 llm_detector_throttle_advisor | Yes | DetectResult.counterfactual; tool_get_detector_recommendation calls detector_backend.detect(); tests: test_tool_get_detector_recommendation_* (test_detector_throttle_advisor_gating.py), test_detector_false_positive_cap_*, test_detector_true_positive_floor_* (test_detector_advisor_fp_tp.py). |

The sections below remain the **definition of done** for marking each method state-of-the-art (conformance, property tests, scenario, METHOD_TRACE, docs).

## 5.1 llm_central_planner

- Multi-role committee: Allocator agent, Scheduler agent, Router agent, Safety reviewer agent.
- Deterministic arbiter merges and validates; repair request to responsible subagent on invalid.
- Tests: Golden committee trace (offline backend); fault injection (corrupt allocator -> reviewer flags, arbiter rejects, repair converges in N steps).

## 5.2 llm_hierarchical_allocator

- Required outputs: intent_confidence, assumptions, risk_flags.
- Controller uses confidence to accept or fall back to kernel; assumption mismatch -> reject + repair.
- Tests: Low confidence -> fallback; assumption mismatch -> reject + repair.

## 5.3 llm_auction_bidder

- Explainable typed bids: decomposition (travel_time_estimate, queue_delay_estimate, risk_penalty, fairness_penalty).
- System recomputes and rejects inconsistent bids beyond tolerance.
- Tests: Bid inconsistency rejection; adversarial prompt in digest -> no schema escape or tool misuse.

## 5.4 llm_gossip_summarizer

- Summary + hash commitments to raw fields; validate by recomputing hashes from raw obs.
- Reject mismatch; reject overlong.
- Tests: Poisoned summary cannot change counts undetected; overlong -> reject + fallback.

## 5.5 llm_repair_over_kernel_whca

- LLM proposes 3–10 candidate repairs; validator scores (collision-free, SLA, fairness); select best; else safe fallback.
- Tests: Candidate set with invalid and valid -> choose valid; deterministic backend -> identical chosen repair.

## 5.6 llm_detector_throttle_advisor

- Detector outputs probability + abstain; optional counterfactual.
- Gate enforcement on probability threshold, policy scope, cooldown.
- Tests: False-positive cap (clean fixtures); true-positive floor (injected fixtures); AgentBench-style sweep.
- **SOTA status:** In pass_budget and pass_evidence. Strictly-better test: `test_llm_detector_throttle_advisor_at_least_as_good_as_kernel_auction_whca_shielded_throughput` (coord_risk, INJ-COMMS-POISON-001). Envelope in `detector_advisor.py` docstring and `coordination_methods.v0.1.yaml` (# compute_envelope).

## Global requirement

Before marking any method state-of-the-art: passes conformance suite (all 5 contracts), method-specific property tests, at least one scenario where it is strictly better than baseline, METHOD_TRACE.jsonl stable to diff, documented compute/latency envelope and fallback strategy.
