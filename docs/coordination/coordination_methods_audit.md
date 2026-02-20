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

## Multi-backend configuration (per-role backends)

When a run uses coordination methods that invoke multiple LLM roles (e.g. planner, bidder, repair, detector), you can assign different backends or models per role so that "planner = model A, bidder = model B" in one run.

**Schema:**

- **llm_backend** (existing): Default backend for all roles when per-role is not set. Values: `openai_live`, `ollama_live`, `anthropic_live`, `openai_responses`, `deterministic`, etc.
- **llm_model** (existing): Default model id (e.g. `gpt-4o-mini`) when using a live backend; overrides env such as `LABTRUST_OPENAI_MODEL`.
- **Per-role backend overrides** (optional): If set, the runner uses this backend for that role instead of `llm_backend`. If unset or `"inherit"`, the role uses `llm_backend`.
  - `coord_planner_backend`: Backend for proposal/allocator (llm_central_planner, llm_hierarchical_allocator).
  - `coord_bidder_backend`: Backend for bid (llm_auction_bidder).
  - `coord_repair_backend`: Backend for repair (llm_repair_over_kernel_whca).
  - `coord_detector_backend`: Backend for detector (llm_detector_throttle_advisor).
  Values: same as `llm_backend` (e.g. `openai_live`, `anthropic_live`, `ollama_live`) or `"inherit"`.
- **Per-role model overrides** (optional): If set, the runner uses this model for that role instead of `llm_model`.
  - `coord_planner_model`, `coord_bidder_model`, `coord_repair_model`, `coord_detector_model`.
  Values: model id string or `"inherit"`.

**Backward compatibility:** When no per-role keys are set, behavior is unchanged: one `llm_backend` (and optionally `llm_model`) for the whole run. All coordinator roles share that backend and model.

**Where config is read:** Runner and CLI. Use `run-benchmark` with `--coord-planner-backend`, `--coord-bidder-backend`, `--coord-repair-backend`, `--coord-detector-backend` (values: `inherit`, `openai_live`, `ollama_live`, `anthropic_live`, etc.) and optionally `--coord-planner-model`, `--coord-bidder-model`, `--coord-repair-model`, `--coord-detector-model`. See [Live LLM](../agents/llm_live.md).

## References

- Runner: `src/labtrust_gym/benchmarks/runner.py` (coordination method branches ~1037–1310).
- Registry: `src/labtrust_gym/baselines/coordination/registry.py`.
- Study runner LLM_METHOD_IDS: `src/labtrust_gym/studies/coordination_study_runner.py`.
