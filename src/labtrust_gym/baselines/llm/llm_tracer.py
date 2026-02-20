"""
LLM observability: spans and trace export (SOTA).

- Span interface: start_span(name), end_span(), set_attribute(k, v).
- In-memory collector when LABTRUST_LLM_TRACE=1; optional file export with
  redaction (no full prompt/response; hashes, lengths, latency, tokens).
- When LABTRUST_OTEL_EXPORTER_OTLP_ENDPOINT is set (and [otel] extra installed),
  spans are also exported to OTLP.
- build_attribution_summary() aggregates cost/latency per agent_id and backend_id.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

LOG = logging.getLogger(__name__)


def _trace_enabled() -> bool:
    raw = (os.environ.get("LABTRUST_LLM_TRACE") or "").strip().lower()
    return raw in ("1", "true", "yes")


def _trace_file_path() -> str | None:
    p = (os.environ.get("LABTRUST_LLM_TRACE_FILE") or "").strip()
    return p or None


def _otel_endpoint() -> str | None:
    e = (os.environ.get("LABTRUST_OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    return e or None


def _get_otel_tracer():  # type: ignore[no-untyped-def]
    """Return OpenTelemetry tracer when endpoint set and [otel] installed; else None."""
    if not _otel_endpoint():
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = _otel_endpoint()
        provider = TracerProvider()
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        return provider.get_tracer("labtrust_gym.llm", "0.1.0")
    except ImportError:
        LOG.warning(
            "LABTRUST_OTEL_EXPORTER_OTLP_ENDPOINT is set but opentelemetry packages "
            "not installed. Install with: pip install -e '.[otel]'"
        )
        return None
    except Exception as e:
        LOG.warning("OTLP tracer setup failed: %s", e)
        return None


class _Span:
    """Single span: name, start time, attributes, end time, status; optional OTel span."""

    __slots__ = (
        "name",
        "start_ns",
        "attrs",
        "end_ns",
        "status",
        "error_message",
        "_otel_span",
    )

    def __init__(self, name: str, otel_span: Any = None) -> None:
        self.name = name
        self.start_ns = time.perf_counter_ns()
        self.attrs: dict[str, Any] = {}
        self.end_ns: int | None = None
        self.status: str = "ok"
        self.error_message: str | None = None
        self._otel_span = otel_span

    def set_attribute(self, key: str, value: Any) -> None:
        self.attrs[key] = value
        if self._otel_span is not None:
            try:
                if isinstance(value, (int, float)):
                    self._otel_span.set_attribute(key, value)
                else:
                    self._otel_span.set_attribute(key, str(value))
            except Exception as e:
                LOG.debug("Tracing set_attribute failed: %s", e)

    def end(
        self, status: str = "ok", error_message: str | None = None
    ) -> None:
        self.end_ns = time.perf_counter_ns()
        self.status = status
        self.error_message = error_message
        if self._otel_span is not None:
            try:
                from opentelemetry.trace import Status, StatusCode

                if status != "ok":
                    self._otel_span.set_status(
                        Status(StatusCode.ERROR, error_message or status)
                    )
                else:
                    self._otel_span.set_status(Status(StatusCode.OK))
                self._otel_span.end()
            except Exception as e:
                LOG.debug("Tracing span end failed: %s", e)
            self._otel_span = None

    def to_export_dict(self, redact: bool = True) -> dict[str, Any]:
        """Export for trace file; redact=True omits full content."""
        out: dict[str, Any] = {
            "name": self.name,
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
            "status": self.status,
            "attrs": dict(self.attrs),
        }
        if self.error_message:
            msg = self.error_message
            out["error_message"] = msg[:200] + "..." if len(msg) > 200 else msg
        if redact:
            for k in list(out["attrs"]):
                if k in ("prompt_content", "response_content", "messages"):
                    del out["attrs"][k]
        return out


class LLMTracer:
    """In-memory span collector; optional file (JSONL); optional OTLP export."""

    def __init__(self) -> None:
        self._spans: list[_Span] = []
        self._current: _Span | None = None
        self._trace_file: str | None = _trace_file_path()
        self._otel_tracer = _get_otel_tracer()

    def start_span(self, name: str) -> None:
        otel_span = None
        if self._otel_tracer is not None:
            try:
                otel_span = self._otel_tracer.start_span(name)
            except Exception as e:
                LOG.debug("OTEL start_span failed: %s", e)
        self._current = _Span(name, otel_span=otel_span)

    def set_attribute(self, key: str, value: Any) -> None:
        if self._current is not None:
            self._current.set_attribute(key, value)

    def end_span(
        self, status: str = "ok", error_message: str | None = None
    ) -> None:
        if self._current is not None:
            self._current.end(status=status, error_message=error_message)
            self._spans.append(self._current)
            if self._trace_file:
                try:
                    with open(self._trace_file, "a", encoding="utf-8") as f:
                        line = json.dumps(self._current.to_export_dict()) + "\n"
                        f.write(line)
                except Exception as e:
                    LOG.debug("Trace file write failed: %s", e)
            self._current = None

    def get_spans(self) -> list[dict[str, Any]]:
        """Return list of span export dicts (redacted)."""
        return [s.to_export_dict() for s in self._spans]

    def get_attribution_summary(self) -> dict[str, Any]:
        """
        Aggregate latency and cost per agent_id and per backend_id from current spans.
        Use for episode metadata or a dedicated artifact.
        """
        return build_attribution_summary(self.get_spans())

    def clear(self) -> None:
        self._spans.clear()
        self._current = None


def build_attribution_summary(spans: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build per-agent and per-backend cost/latency summary from span export dicts.
    Keys: by_agent, by_backend. Each value is a dict of id -> {latency_ms_sum,
    cost_usd_sum, call_count}. Span attrs may include agent_id, backend_id,
    latency_ms, estimated_cost_usd.
    """
    by_agent: dict[str, dict[str, Any]] = {}
    by_backend: dict[str, dict[str, Any]] = {}

    def add(
        key: str,
        store: dict[str, dict[str, Any]],
        latency_ms: float | None,
        cost_usd: float | None,
    ) -> None:
        if not key:
            return
        if key not in store:
            store[key] = {"latency_ms_sum": 0.0, "cost_usd_sum": 0.0, "call_count": 0}
        store[key]["call_count"] += 1
        if latency_ms is not None and isinstance(latency_ms, (int, float)):
            store[key]["latency_ms_sum"] += float(latency_ms)
        if cost_usd is not None and isinstance(cost_usd, (int, float)):
            store[key]["cost_usd_sum"] += float(cost_usd)

    for s in spans:
        attrs = s.get("attrs") or {}
        agent_id = attrs.get("agent_id")
        if agent_id is not None:
            agent_id = str(agent_id).strip()
        backend_id = attrs.get("backend_id")
        if backend_id is not None:
            backend_id = str(backend_id).strip()
        latency_ms = attrs.get("latency_ms")
        cost_usd = attrs.get("estimated_cost_usd")
        add(agent_id or "unknown", by_agent, latency_ms, cost_usd)
        add(backend_id or "unknown", by_backend, latency_ms, cost_usd)

    return {"by_agent": by_agent, "by_backend": by_backend}


_global_tracer: LLMTracer | None = None


def get_llm_tracer() -> LLMTracer | None:
    """Return global tracer when LABTRUST_LLM_TRACE=1, else None."""
    global _global_tracer
    if not _trace_enabled():
        return None
    if _global_tracer is None:
        _global_tracer = LLMTracer()
    return _global_tracer


def record_deterministic_coord_span(
    span_name: str,
    backend_id: str,
    model_id: str = "n/a",
    latency_ms: float = 0.0,
    estimated_cost_usd: float = 0.0,
) -> None:
    """Record a span for a deterministic coord backend so attribution by_backend includes it."""
    tracer = get_llm_tracer()
    if tracer is None:
        return
    tracer.start_span(span_name)
    tracer.set_attribute("backend_id", backend_id)
    tracer.set_attribute("model_id", model_id)
    tracer.set_attribute("latency_ms", latency_ms)
    tracer.set_attribute("estimated_cost_usd", estimated_cost_usd)
    tracer.end_span()
