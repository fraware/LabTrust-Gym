# Coordination LLM Card (LLM-based methods)

This card lists LLM-based coordination methods, supported backends, policy fingerprint, injection coverage for security evaluation, and known limitations. For the full coordination protocol see docs/llm_coordination_protocol.md in the repository.

## LLM coordination methods

| method_id | name | known_weaknesses | required_controls |
|-----------|------|------------------|-------------------|
| llm_constrained | LLM constrained (existing baseline) | R-TOOL-001, R-TOOL-005, R-CAP-001, R-DATA-001 | signed_actions, RBAC, rate_limit |
| llm_central_planner | LLM central planner (global state digest -> CoordinationProposal) | R-TOOL-001, R-TOOL-005, R-CAP-001, R-DATA-001 | signed_actions, RBAC, rate_limit |
| llm_hierarchical_allocator | LLM hierarchical allocator (assignments -> local controller greedy/EDF/WHCA) | R-TOOL-001, R-TOOL-005, R-CAP-001, R-DATA-001, R-COMMS-002 | signed_actions, RBAC, rate_limit |
| llm_auction_bidder | LLM auction bidder (typed bids -> deterministic auction -> dispatcher) | R-DATA-001, R-COMMS-002, R-TOOL-006 | signed_actions, RBAC, rate_limit, bid_validation |
| llm_gossip_summarizer | LLM gossip summarizer (signed typed messages, deterministic consensus) | R-COMMS-002, R-DATA-001, R-SYS-002 | signed_actions, RBAC, message_auth, replay_protection |

## Backends

| backend_id | description |
|------------|-------------|
| deterministic | Seeded proposal backend; no network; reproducible. |
| openai_live | Live OpenAI (CoordinationProposal or market bids); used by llm_central_planner, llm_hierarchical_allocator, llm_auction_bidder; requires OPENAI_API_KEY. |
| ollama_live | Live Ollama (CoordinationProposal or market bids); same methods as openai_live when configured (LABTRUST_LOCAL_LLM_URL, LABTRUST_LOCAL_LLM_MODEL). |

Default for `run-coordination-study` and `run-benchmark` when using LLM methods: **deterministic**. No API calls unless `--llm-backend openai_live` (or ollama_live) is passed.

## Policy fingerprint

Same as coordination policy: **SHA-256** `ea7f93994560ef4f8a819b8d3bcad195753c50423e807b07f466f517cb384593` (see COORDINATION_CARD.md for per-file hashes).

## Injection coverage (security evaluation)

coord_risk injections used for security evaluation (from injections.v0.2.yaml):

- INJ-BID-SPOOF-001
- INJ-BLAME-SHIFT-001
- INJ-COLLUSION-001
- INJ-COLLUSION-MARKET-001
- INJ-COMMS-FLOOD-LLM-001
- INJ-COMMS-POISON-001
- INJ-CONSENSUS-POISON-001
- INJ-COORD-BID-SHILL-001
- INJ-COORD-PLAN-REPLAY-001
- INJ-COORD-PROMPT-INJECT-001
- INJ-ID-REPLAY-COORD-001
- INJ-ID-SPOOF-001
- INJ-LLM-PROMPT-INJECT-COORD-001
- INJ-LLM-TOOL-ESCALATION-001
- INJ-MEMORY-POISON-001
- INJ-MEMORY-POISON-COORD-001
- INJ-PARTIAL-OBS-001
- INJ-REPLAY-001
- INJ-SLOW-POISON-001
- INJ-TIMING-QUEUE-001
- inj_dos_flood
- inj_memory_tamper
- inj_tool_selection_noise

LLM-relevant injections include: INJ-LLM-PROMPT-INJECT-COORD-001, INJ-LLM-TOOL-ESCALATION-001, INJ-COMMS-FLOOD-LLM-001, INJ-ID-REPLAY-COORD-001, INJ-COLLUSION-MARKET-001, INJ-MEMORY-POISON-COORD-001, INJ-ID-SPOOF-001, INJ-COMMS-POISON-001, INJ-BID-SPOOF-001, INJ-COLLUSION-001, and others as defined in the spec.

Method-risk matrix (required_bench / coverage) for LLM methods is in policy/coordination/method_risk_matrix.v0.1.yaml. Run with `--llm-backend deterministic` to satisfy coverage gates without network.

## Known limitations

- **Deterministic backend**: Proposals are seeded NOOP or trivial; not representative of live LLM quality. Use for reproducibility and coverage only.
- **Live backends**: Require API key (openai_live) or local service (ollama_live); cost and latency vary; results non-deterministic.
- **Shield and repair**: LLM proposals are passed through RBAC/signature shield; blocked actions trigger repair loop. Repair caps (max_repairs, blocked_threshold) are configurable via scale_config. Security metrics (attack_success_rate, detection, containment) depend on injection and harness.
- **Injection set**: Only configured injections in the study spec are applied; no black-box adversary search.
