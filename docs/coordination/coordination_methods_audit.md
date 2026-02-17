# Coordination methods audit (LLM methods)

Audit table for each coordination method with `coordination_class: llm`: runner live-backend support, backend parameter, prompts location, scaling notes, and study inclusion. Used to drive wiring of live backends (openai_live, ollama_live, anthropic_live) and LLM-only workflow.

| method_id | live_backend_in_runner | backend_param | prompts_location | scaling_notes | in_LLM_METHOD_IDS |
|-----------|------------------------|---------------|------------------|---------------|-------------------|
| llm_constrained | Y | llm_agent (holds backend) | policy/llm, agent prompts | One LLM call per agent per step; scales with num_agents | Y |
| llm_central_planner | Y | proposal_backend | policy/llm, openai_responses_backend | Central proposal; token budget scales with queue/agents summary | Y |
| llm_central_planner_shielded | Y | (variant) | same | same | Y |
| llm_central_planner_with_safe_fallback | Y | (variant) | same | same | Y |
| llm_hierarchical_allocator | Y | allocator_backend | policy/llm, openai_responses_backend | Hub allocates; scale by regions/agents | Y |
| llm_hierarchical_allocator_shielded | Y | (variant) | same | same | Y |
| llm_hierarchical_allocator_with_safe_fallback | Y | (variant) | same | same | Y |
| llm_auction_bidder | Y | bid_backend | policy/llm, openai_bid_backend | One bid per agent per round; scale with agents | Y |
| llm_auction_bidder_shielded | Y | (variant) | same | same | Y |
| llm_auction_bidder_with_safe_fallback | Y | (variant) | same | same | Y |
| llm_gossip_summarizer | Y | summary_backend (optional) | OpenAI/Ollama gossip summary backend | Optional LLM summary; fallback to local summary | Y |
| llm_repair_over_kernel_whca | Y | repair_backend | agent.py REPAIR_SYSTEM_PROMPT, repair user content | Repair only when kernel blocks; low call rate | Y |
| llm_local_decider_signed_bus | Y | proposal_backend (registry default) | N/A when deterministic backend | Per-agent proposal; scales with agents | Y |
| llm_detector_throttle_advisor | Y | detector_backend (optional) | LiveDetectorBackend prompt when live | Detector runs each step; optional live LLM backend | Y |

## Backend interfaces

- **llm_constrained**: Accepts `llm_agent` (LLMAgentWithShield). The agent wraps a backend implementing `generate(messages) -> str`. Runner currently builds `DeterministicConstrainedBackend` only; live path: build `OpenAILiveBackend` / `OllamaLiveBackend` and pass to `LLMAgentWithShield(backend=..., ...)`.
- **llm_central_planner**: Accepts `proposal_backend` (e.g. OpenAICoordinationProposalBackend, OllamaCoordinationProposalBackend). Live path present for openai_live and ollama_live.
- **llm_hierarchical_allocator**: Accepts `allocator_backend` (same interface as proposal). Live path present.
- **llm_auction_bidder**: Accepts `bid_backend` (OpenAIBidBackend, OllamaBidBackend). Live path present.
- **llm_gossip_summarizer**: No backend parameter; uses deterministic `_build_local_summary`. To support live: add optional `summary_backend` (e.g. get_summary(agent_id, obs, zone_ids, device_ids, t) -> payload dict) and wire in runner.
- **llm_local_decider_signed_bus**: Accepts `proposal_backend` with `propose_action(local_view, allowed_actions, agent_id, step) -> dict`. Registry defaults to DeterministicLocalProposalBackend; runner does not pass live backend. Live path: build backend implementing that interface and pass via make_coordination_method params.
- **llm_repair_over_kernel_whca**: Accepts `repair_backend` with `generate(messages) -> str`. Registry defaults to DeterministicRepairBackend; runner does not pass live backend. Live path: build OpenAILiveBackend or equivalent and pass as repair_backend in params.
- **llm_detector_throttle_advisor**: Built with `wrap_with_detector_advisor(inner, detector_backend)`. Registry accepts `detector_backend` from params; defaults to DeterministicDetectorBackend. Live path: runner passes LiveDetectorBackend(OpenAILiveBackend/OllamaLiveBackend/AnthropicLiveBackend) when llm_backend is openai_live, ollama_live, or anthropic_live.

## References

- Runner: `src/labtrust_gym/benchmarks/runner.py` (coordination method branches ~1037–1310).
- Registry: `src/labtrust_gym/baselines/coordination/registry.py`.
- Study runner LLM_METHOD_IDS: `src/labtrust_gym/studies/coordination_study_runner.py`.
