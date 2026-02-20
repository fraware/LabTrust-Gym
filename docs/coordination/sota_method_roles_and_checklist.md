# SOTA Method Roles and Checklist

This document classifies coordination methods by role (Primary, Experimental/variants, Baselines, Legacy) and tracks the SOTA checklist per method. It supports refinement without removal: all methods stay; roles and checklist status guide improvement.

## Method roles

### Primary methods (Tier 1–2)

Full SOTA checklist expected; main targets for the hospital workflow and papers.

| method_id | Role | Notes |
|-----------|------|--------|
| llm_repair_over_kernel_whca | Primary (poster child) | Kernel + LLM repair; INJ-COMMS-POISON, ID-SPOOF; repair path capped under budget |
| llm_central_planner | Primary | Global digest to single proposal; baseline for central LLM coordination |
| llm_hierarchical_allocator | Primary | LLM assignments to local controller (EDF/WHCA) |
| llm_auction_bidder | Primary | LLM bids, deterministic auction, dispatcher |
| llm_local_decider_signed_bus | Primary | Per-agent proposals over signed bus; deterministic reconciler + shield |
| llm_detector_throttle_advisor | Primary | Wraps kernel_auction_whca_shielded; detect + policy-validated containment |

### Experimental / variants

Same as base method plus defense profile (shielded, safe_fallback). Refinement: scenarios under attack, envelope.

| method_id | Base | Notes |
|-----------|------|--------|
| llm_central_planner_shielded | llm_central_planner | Strict validation, safe fallback on reject |
| llm_hierarchical_allocator_shielded | llm_hierarchical_allocator | Shielded variant |
| llm_auction_bidder_shielded | llm_auction_bidder | Shielded variant |
| llm_central_planner_with_safe_fallback | llm_central_planner | Explicit safe fallback on error |
| llm_hierarchical_allocator_with_safe_fallback | llm_hierarchical_allocator | Safe fallback |
| llm_auction_bidder_with_safe_fallback | llm_auction_bidder | Safe fallback |
| llm_central_planner_debate | llm_central_planner | N proposers, majority aggregate |
| llm_central_planner_agentic | llm_central_planner | Bounded tool rounds per step |

### Baselines (kernel / deterministic)

Reference and building blocks; no LLM. Used as comparison baselines in strictly-better tests.

| method_id | Notes |
|-----------|--------|
| kernel_whca | Composed alloc + EDF + WHCA* router; used inside llm_repair |
| kernel_centralized_edf | Alloc + EDF + trivial router |
| kernel_scheduler_or | OR scheduler + trivial router |
| kernel_scheduler_or_whca | OR scheduler + WHCA* router |
| kernel_auction_edf | Auction-based kernel |
| kernel_auction_whca | Auction + WHCA* |
| centralized_planner | Single global worklist, greedy assignment; compute_budget knob |
| hierarchical_hub_rr | Hierarchical hub, rapid response |
| hierarchical_hub_local | EDF + route per region |
| market_auction | Market / contract net (auction) |
| gossip_consensus | Gossip consensus (no LLM) |
| ripple_effect | Local intent + signed bus, neighbor propagation |
| consensus_paxos_lite | Global digest, bounded rounds |
| swarm_reactive | Swarm reactive |
| swarm_stigmergy_priority | Stigmergy (priority-weighted pheromone) |
| group_evolving_experience_sharing | Deterministic track experience sharing |

### Legacy / minimal

Minimal or legacy baseline; prefer primary methods for new work.

| method_id | Notes |
|-----------|--------|
| llm_constrained | Wraps LLMAgentWithShield as CoordinationMethod; minimal LLM baseline. Prefer llm_central_planner for new work. |
| llm_gossip_summarizer | LLM summarizer over gossip; in primary comparison set for distributed. |

### Learning / optional

| method_id | Notes |
|-----------|--------|
| marl_ppo | Requires model_path (trained checkpoint); conformance skipped without it. Optional_deps_methods. |
| group_evolving_study | Population evolution across episodes; optional_deps_methods. |

---

## SOTA checklist (refinement dashboard)

For each method, the checklist tracks: conformance (pass_budget, pass_evidence), strictly-better scenario test, envelope in YAML, envelope in docstring. Trace is produced by the runner for all methods when run via study/pack; no per-method column needed.

| method_id | pass_budget | pass_evidence | strictly_better_test | envelope_yaml | envelope_docstring |
|-----------|-------------|---------------|------------------------|---------------|---------------------|
| llm_repair_over_kernel_whca | Y | Y | Y (vs kernel_whca under poison) | Y | Y |
| llm_central_planner | Y | Y | Y (vs kernel_whca) | Y | Y |
| llm_hierarchical_allocator | Y | Y | Y (vs hierarchical_hub_rr) | Y | Y |
| llm_auction_bidder | Y | Y | Y (vs market_auction) | Y | Y |
| llm_gossip_summarizer | Y | Y | Y (vs gossip_consensus) | Y | Y |
| llm_local_decider_signed_bus | Y | Y | Y (vs ripple_effect) | Y | Y |
| llm_constrained | Y | Y | N (legacy) | Y | Y |
| kernel_whca | Y | (runner trace) | baseline | Y | (compose) |
| centralized_planner | Y | Y | baseline | Y | Y |
| hierarchical_hub_rr | Y | Y | baseline | Y | Y |
| hierarchical_hub_local | Y | Y | baseline | Y | Y |
| market_auction | Y | Y | baseline | Y | Y |
| gossip_consensus | Y | Y | baseline | Y | Y |
| ripple_effect | Y | Y | baseline | N | Y |
| consensus_paxos_lite | Y | Y | baseline | Y | Y |
| swarm_reactive | Y | Y | baseline | Y | Y |
| swarm_stigmergy_priority | Y | Y | baseline | Y | Y |
| group_evolving_experience_sharing | Y | Y | baseline | (comment) | N |
| llm_detector_throttle_advisor | Y | Y | Y (vs kernel_auction_whca_shielded under poison) | Y | Y |

Shielded and safe_fallback variants (llm_central_planner_shielded, llm_central_planner_with_safe_fallback, llm_hierarchical_allocator_shielded, llm_hierarchical_allocator_with_safe_fallback, llm_auction_bidder_shielded, llm_auction_bidder_with_safe_fallback) each have a strictly-better scenario under INJ-COMMS-POISON-001 in `tests/test_coord_strictly_better.py`. They are not in pass_budget/pass_evidence (they resolve to the base method in conformance). For the full table including all policy method_ids, run `python scripts/refresh_sota_checklist.py`.

**Conformance source:** `tests/coord_methods/conformance/conformance_config.yaml` (pass_budget, pass_evidence). **Strictly-better tests:** `tests/test_coord_strictly_better.py`. **Envelope:** `policy/coordination/coordination_methods.v0.1.yaml` (# compute_envelope) and module docstrings in `src/labtrust_gym/baselines/coordination/methods/*.py`.

To refresh this table: run `python scripts/refresh_sota_checklist.py` from repo root (reads conformance_config.yaml, test_coord_strictly_better.py, coordination_methods.v0.1.yaml, and method docstrings), or manually: run the conformance matrix; grep pass_budget/pass_evidence from conformance_config.yaml; grep coord_method from test_coord_strictly_better.py (variant = second run per test); grep "compute_envelope" from coordination_methods.v0.1.yaml and "Envelope (SOTA audit)" from method docstrings.
