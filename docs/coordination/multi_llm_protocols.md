# Multi-LLM coordination protocols (design)

This document describes a design for coordination protocols where multiple LLM instances interact (e.g. round-by-round bidding, handoffs) or the coordinator uses a multi-step agentic loop. The current codebase uses a single logical backend per run and one call per step per role; this design extends toward multi-step and multi-LLM protocols.

## Goals

- **Round-by-round bidding:** Auctioneer announces work items; each bidder LLM returns a bid; auctioneer aggregates. Multiple round-trips per env step; distinct auctioneer vs bidder backends possible (Phase 2 per-role config).
- **Handoffs:** Planner LLM produces a high-level plan; repair LLM refines only blocked parts; detector LLM can suggest throttle. Clear message format and when each backend is invoked.
- **Debate / consensus (optional):** Multiple LLM agents each propose; another LLM or deterministic rule aggregates. Scope kept small (e.g. one method like llm_auction_bidder).

## Compatibility with CoordinationMethod

The current interface is:

- `propose_actions(obs, infos, t) -> dict[agent_id, action_dict]`
- Kernel-composed methods: `step(context) -> (actions_dict, CoordinationDecision)`

Two ways to fit multi-step protocols:

1. **Orchestrator pattern:** One coordination method implements `propose_actions` and internally runs the multi-step protocol (e.g. N bidder calls, then aggregate). It still returns one `actions_dict` per env step. The runner does not change; only the method’s internal loop changes.
2. **Extended interface (future):** Allow multiple “sub-steps” or “rounds” per env step with a bounded budget (e.g. `max_rounds_per_step`). The runner would call into the method in a loop until the method signals “done” or the budget is exhausted. This would require runner and interface changes.

Recommendation: start with (1). Implement round-by-round auction as an optional mode inside `llm_auction_bidder`: when `COORD_AUCTION_PROTOCOL=round_robin`, the method calls the bid backend once per agent (or per group), then aggregates and returns one `actions_dict`. Same `propose_actions` signature; no runner change.

## Round-by-round bidding (concrete)

- **Current (single_call):** One `generate_proposal(state_digest, step_id, method_id)` returns a full proposal with `market[]` containing all bids.
- **Round-robin mode (implemented):** Set `scale_config["coord_auction_protocol"] = "round_robin"` or env `COORD_AUCTION_PROTOCOL=round_robin`. For each agent, the method calls the bid backend with a digest scoped to that agent and collects one bid per call. Bids are merged into a single `market[]` and the same clearing and dispatcher logic runs. So N calls per step instead of one; same backend or per-role bidder backend (Phase 2). See `llm_auction_bidder.propose_actions` and tests in `test_coord_llm_auction_bidder_smoke.py`.
- **Message format:** Each bidder call receives a state digest (possibly scoped to that agent) and returns a single bid or a small struct; the orchestrator merges them into the existing proposal schema so downstream (clearing, shield, executor) is unchanged.
- **Safety and observability:** Each bidder call goes through the same coordinator guardrails (Phase 1.2) and tracing (Phase 1.3). Span names can be `coord_bid` with an attribute `agent_id` or `round_index` to distinguish calls.

## Handoffs (planner / repair / detector) — specified

The message envelope and invocation order are specified in [Handoff protocol](handoff_protocol.md).

- **Planner:** Produces high-level plan (e.g. allocation + schedule sketch). Output is a structured message (e.g. same as current proposal but marked “high-level”).
- **Repair:** Invoked when the kernel or shield blocks. Receives “blocked actions + context” and returns repaired actions. Already implemented; handoff is “runner calls planner path, then on block calls repair path.” See [Handoff protocol](handoff_protocol.md) for `repair_input` schema.
- **Detector:** Observes step outcomes and can suggest throttle or enforcement. Can be a separate LLM call each step (current detector_advisor) or triggered on certain events. See [Handoff protocol](handoff_protocol.md) for event_summary and DetectorOutput.
- **Unification:** All three use the same per-role backends (Phase 2) and guardrails/tracing (Phase 1).

## Debate / consensus — implemented

- Implemented in **llm_central_planner_debate**: N proposer backends (coord_debate_proposers), majority vote per agent. See llm_central_planner_debate.py and test_coord_llm_debate_smoke.py.
- Multiple “proposer” LLMs each produce a proposal; one “aggregator” LLM or a deterministic rule (e.g. majority vote on action_type per agent) produces the final proposal. Scope: one method (e.g. a variant of llm_central_planner or llm_auction_bidder) to avoid touching the rest of the codebase.
- Aggregator can be another backend (Phase 2: e.g. `coord_aggregator_backend`) or a small Python rule. Guardrails and tracing apply to each proposer and the aggregator.

## Safety and observability

- **Guardrails:** Phase 1.2 coordinator guardrails (circuit breaker, rate limit) apply to every coordinator LLM call. In a multi-step protocol, each step (e.g. each bidder call) is one “call” for rate-limit and circuit-breaker purposes.
- **Tracing:** Phase 1.3 ensures every coordinator backend emits spans with `backend_id` and role-identifying attributes. Attribution summary `by_backend` (and optional `by_role`) already supports multiple backends in one run (Phase 2.3).

## Coordinator agentic loop (ReAct / tools) — implemented

A future extension is a “coordinator with tools”: the coordinator LLM can request “query queue state,” “simulate allocation,” “ask detector,” etc., with a **bounded number of tool calls per env step**.

- **Interface:** Still one `propose_actions(obs, infos, t)` per step. Internally, the method runs a loop: call LLM -> if tool_use then execute tool(s) and append results to context -> call LLM again, until “final proposal” or max tool rounds.
- **Tools:** Implemented as functions that take (env, obs, infos, step_t, method_state) and return a small result (e.g. queue state, detector recommendation). No env step is executed until the method returns the final actions_dict.
- **Guardrails and observability:** Each LLM call in the loop is a coordinator call: same circuit breaker, rate limit, and tracing. Span names could be `coord_agentic` with `round` attribute. Bounded rounds (e.g. max 5 tool rounds per step) keep latency and cost predictable.

Implemented in llm_central_planner_agentic; see coord_agentic_tools.py and test_coord_llm_agentic_smoke.py.

## Per-role live test (implemented)

A live test runs with distinct backends per role and asserts attribution: `test_openai_live_coord_scale_per_role_backends` in `tests/test_openai_live.py`. It uses `coord_planner_backend=openai_live` and `coord_bidder_backend=anthropic_live` for `llm_auction_bidder`, sets `LABTRUST_LLM_TRACE=1`, and asserts `metadata.llm_attribution_summary.by_backend` contains at least two distinct backend IDs with call/latency/cost stats. Requires `LABTRUST_RUN_LLM_LIVE=1`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY`. Run with: `pytest tests/test_openai_live.py -m live -k per_role -v`.

## Limitations (current behavior) and state of the art

- **Debate:** Aggregation is deterministic (majority vote per agent). An optional LLM aggregator is future work. State-of-the-art multi-agent debate in the literature often uses a dedicated aggregator LLM or iterative refinement; our implementation is intentionally minimal and extensible.
- **Round_robin:** N bidder calls per step then merge; no true multi-round negotiation or message-passing between separate agent LLMs. True multi-agent negotiation would require multiple rounds of message exchange and agreement protocols; the current design prioritizes one-step orchestration and clear attribution.
- **Trials and reporting:** coord_scale and coord_risk are both supported by the trials script; the interpretation template (see [LLM coordinator trials](../reference/llm_coord_trials.md)) provides a written summary structure. A single published document that interprets a specific run (cost, latency, conclusions) is filled in by the user from that template.

## Future work (optional)

- **Debate aggregator LLM:** An optional aggregator backend (e.g. `coord_debate_aggregator_backend`) could be added so a second LLM aggregates N proposals instead of a Python majority vote.
- **Lab policies:** The same lab policies (RBAC, shield, invariants) apply to both deterministic and LLM coordination paths; no separate policy layer is introduced for LLM coordinators.
