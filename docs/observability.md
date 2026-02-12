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

## Default behavior

- Tracing is **off** unless `LABTRUST_LLM_TRACE` is set.
- OTLP export is **off** unless `LABTRUST_OTEL_EXPORTER_OTLP_ENDPOINT` is set (and `[otel]` is installed).
- When tracing is off, no spans are collected and no attribution summary is written; benchmark behavior and performance are unchanged.

## See also

- [Live LLM](llm_live.md): pipeline modes, backends, and environment variables for live providers.
- Episode log: each step can include `_llm_decision` with per-call meta (`backend_id`, `model_id`, `latency_ms`, tokens).
