# LLM observability: tracing and cost/latency attribution

This document describes how to enable LLM tracing, export spans to OpenTelemetry (OTLP), and use cost/latency attribution per agent and backend.

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LABTRUST_LLM_TRACE` | Set to `1`, `true`, or `yes` to enable in-memory span collection and optional file/OTLP export. | (unset) |
| `LABTRUST_LLM_TRACE_FILE` | When set, each span is appended as one JSONL line (redacted: no full prompt/response; hashes, lengths, latency, tokens). | (unset) |
| `LABTRUST_OTEL_EXPORTER_OTLP_ENDPOINT` | When set and the `[otel]` extra is installed, spans are also exported to this OTLP HTTP endpoint (e.g. `https://api.example.com/v1/traces`). | (unset) |

**Install OTLP support:** `pip install -e ".[otel]"`. If the endpoint is set but the packages are not installed, a warning is logged and tracing continues without OTLP.

## Span attributes

Spans record (when available):

- `backend_id`, `model_id`: LLM backend and model.
- `agent_id`: Agent that triggered the call (when provided in context).
- `latency_ms`: Call latency in milliseconds.
- `prompt_tokens`, `completion_tokens`: Token usage.
- `estimated_cost_usd`: Estimated cost in USD (when model pricing is configured; e.g. openai_live with `policy/model_pricing.v0.1.yaml`).

These appear in in-memory spans, trace file JSONL, OTLP export, and in each LLM_DECISION audit event in the episode log (meta: `backend_id`, `model_id`, `latency_ms`, `prompt_tokens`, `completion_tokens`).

## Cost and latency attribution summary

When `LABTRUST_LLM_TRACE=1` and a benchmark run completes, the runner writes an **attribution summary** into `results.json` under `metadata.llm_attribution_summary`. The structure is:

```json
{
  "by_agent": {
    "agent_id": {
      "latency_ms_sum": 1234.5,
      "cost_usd_sum": 0.002,
      "call_count": 10
    }
  },
  "by_backend": {
    "backend_id": {
      "latency_ms_sum": 1234.5,
      "cost_usd_sum": 0.002,
      "call_count": 10
    }
  }
}
```

You can also build this from span data yourself:

```python
from labtrust_gym.baselines.llm.llm_tracer import get_llm_tracer, build_attribution_summary

tracer = get_llm_tracer()
if tracer is not None:
    summary = tracer.get_attribution_summary()  # or build_attribution_summary(tracer.get_spans())
    # Attach summary to episode metadata or write to a dedicated artifact.
```

### Attribution in results

`metadata.llm_attribution_summary` is **only written when tracing is enabled**: set `LABTRUST_LLM_TRACE=1` (or `true` / `yes`) before the run. When tracing is off, the runner does not persist attribution; benchmark behavior is unchanged. E2E tests or analyses that rely on attribution (e.g. asserting `by_backend` call counts or per-role split) must set `LABTRUST_LLM_TRACE=1` in the test process and document this requirement.

## Span coverage

Spans are created only where the code calls `get_llm_tracer()`, `start_span(name)`, and `end_span(...)`.

- **Agent path (generate):** The **openai_live** backend creates one span per LLM call (name `propose_action`) when used for the agent generate path, in `src/labtrust_gym/baselines/llm/backends/openai_live.py`. Attributes: `backend_id`, `model_id`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `estimated_cost_usd` when model pricing is configured.
- **Coordinator backends:** The following coordination LLM call sites are instrumented and appear in attribution (by_backend and, when applicable, by_agent):
  - **coord_proposal:** Proposal backends (central planner, hierarchical allocator). Created in `openai_responses_backend.py` (OpenAICoordinationProposalBackend), `ollama_coordination_backend.py` (OllamaCoordinationProposalBackend). Span name: `coord_proposal`.
  - **coord_bid:** Bid backends (auction). Created in `openai_bid_backend.py` (OpenAIBidBackend), `ollama_coordination_backend.py` (OllamaBidBackend). Span name: `coord_bid`.
  - **coord_repair:** Repair backend (llm_repair_over_kernel_whca). Created in `llm_repair_over_kernel_whca.py` (LiveRepairBackend.repair). Span name: `coord_repair`.
  - **coord_detector:** Detector backend (llm_detector_throttle_advisor). Created in `detector_advisor.py` (LiveDetectorBackend). Span name: `coord_detector`.
  - **coord_agentic:** Agentic coordinator (llm_central_planner_agentic). Created in `openai_agentic_coord_backend.py` (OpenAIAgenticProposalBackend). Span name: `coord_agentic`.
  Each span sets `backend_id` and `model_id` (or a placeholder when unknown); `latency_ms`, `prompt_tokens`, `completion_tokens`, and `estimated_cost_usd` when available. The attribution summary's `by_backend` aggregates all of these, so coordination LLM cost and latency are visible alongside the agent path.
- **Runner:** After a benchmark run, the runner calls `get_llm_tracer()` and, if tracing was enabled and the tracer has spans, writes `metadata.llm_attribution_summary` (by_agent, by_backend) and optionally exports spans to the trace file or OTLP.

So for **llm_live** runs with `LABTRUST_LLM_TRACE=1`, span coverage includes the openai_live agent path and all coordinator backends (proposal, bid, repair, detector, agentic). Attribution summary includes coordination calls under `by_backend` (and by_agent when agent_id is set on the span).

## Sampling and cost attribution

- **Sampling:** There is no sampling; when tracing is on, every instrumented LLM call produces one span. There is no sampling configuration in the repo.
- **Cost:** Cost attribution (`estimated_cost_usd`) is computed when the backend sets it (e.g. openai_live uses **policy/model_pricing.v0.1.yaml** for per-model per-1M-token prices). The attribution summary aggregates `latency_ms_sum` and `cost_usd_sum` per agent_id and backend_id from span attributes. OTLP export sends all spans (no sampling).

## Observability checklist

To verify end-to-end observability for a production-like llm_live run:

1. Set `LABTRUST_LLM_TRACE=1` (and optionally `LABTRUST_LLM_TRACE_FILE=<path>` or `LABTRUST_OTEL_EXPORTER_OTLP_ENDPOINT=<url>`).
2. Run a benchmark with `--pipeline-mode llm_live --allow-network` and an instrumented backend (e.g. openai_live).
3. After the run, confirm **results.json** includes `metadata.llm_attribution_summary` with `by_agent` and `by_backend` (and non-zero `call_count` where applicable).
4. If a trace file was set, confirm the file contains one JSONL line per span (redacted; no full prompt/response).
5. If OTLP endpoint was set and `[otel]` is installed, confirm your collector or backend received the spans.

## Default behavior

- Tracing is **off** unless `LABTRUST_LLM_TRACE` is set.
- OTLP export is **off** unless `LABTRUST_OTEL_EXPORTER_OTLP_ENDPOINT` is set (and `[otel]` is installed).
- When tracing is off, no spans are collected and no attribution summary is written; benchmark behavior and performance are unchanged.

## See also

- [Live LLM](../agents/llm_live.md): pipeline modes, backends, and environment variables for live providers.
- Episode log: each step can include `_llm_decision` with per-call meta (`backend_id`, `model_id`, `latency_ms`, tokens).
