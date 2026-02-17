# Phase 5: LLM Method Upgrades (Definition of Done)

Per-method upgrade requirements from the SOTA coordination plan. Each method must pass the conformance suite and meet the following before being marked state-of-the-art.

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

## Global requirement

Before marking any method state-of-the-art: passes conformance suite (all 5 contracts), method-specific property tests, at least one scenario where it is strictly better than baseline, METHOD_TRACE.jsonl stable to diff, documented compute/latency envelope and fallback strategy.
