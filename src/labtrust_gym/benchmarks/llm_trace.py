"""
LLM trace bundle for live evaluation: redacted requests, responses, fingerprints, usage.

Used by the llm_live_eval profile to store a non-deterministic run trace without
contaminating deterministic baselines. All request content is redacted via
secret_scrubber (API keys, secrets, sensitive fields) before writing.
"""  # noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.security.secret_scrubber import (
    scrub_dict_for_log,
    scrub_secrets,
)


class LLMTraceCollector:
    """
    Collects redacted requests, raw responses, prompt fingerprints, and usage
    for each LLM call. write_to_dir writes LLM_TRACE/ layout.
    """  # noqa: E501

    def __init__(self) -> None:
        self._requests_redacted: list[dict[str, Any]] = []
        self._responses: list[str] = []
        self._prompt_fingerprints: list[dict[str, Any]] = []
        self._usage_list: list[dict[str, Any]] = []

    def record(
        self,
        messages: list[dict[str, Any]],
        response_raw: str,
        prompt_sha256: str,
        usage: dict[str, Any],
    ) -> None:
        """Record one LLM call (request redacted, response, fingerprint, usage)."""
        messages_redacted = self._redact_messages(messages)
        self._requests_redacted.append({"messages": messages_redacted})
        self._responses.append(response_raw)
        idx = len(self._requests_redacted) - 1
        self._prompt_fingerprints.append({"index": idx, "prompt_sha256": prompt_sha256})
        self._usage_list.append(dict(usage))

    def _redact_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Redact secrets from message list (content and secret-like keys)."""
        out: list[dict[str, Any]] = []
        for m in messages:
            copy: dict[str, Any] = dict(m)
            if "content" in copy and isinstance(copy["content"], str):
                copy["content"] = scrub_secrets(copy["content"])
            out.append(scrub_dict_for_log(copy))
        return out

    def write_to_dir(self, dir_path: Path) -> None:
        """Write LLM_TRACE: requests_redacted.jsonl, responses.jsonl, prompt_fingerprints.json, usage.json."""
        dir_path = Path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)

        with open(dir_path / "requests_redacted.jsonl", "w", encoding="utf-8") as f:
            for req in self._requests_redacted:
                f.write(json.dumps(req, sort_keys=True) + "\n")

        with open(dir_path / "responses.jsonl", "w", encoding="utf-8") as f:
            for resp in self._responses:
                # Response is already a string (JSON); write as single line
                f.write(resp.strip() + "\n")

        with open(dir_path / "prompt_fingerprints.json", "w", encoding="utf-8") as f:
            json.dump(self._prompt_fingerprints, f, indent=2, sort_keys=True)

        aggregate = self._aggregate_usage()
        with open(dir_path / "usage.json", "w", encoding="utf-8") as f:
            json.dump(aggregate, f, indent=2, sort_keys=True)

    def _aggregate_usage(self) -> dict[str, Any]:
        """Aggregate usage across all calls; include per-call latency when present."""
        total_prompt = sum(u.get("prompt_tokens", 0) for u in self._usage_list)
        total_completion = sum(u.get("completion_tokens", 0) for u in self._usage_list)
        total_tokens = sum(u.get("total_tokens", 0) for u in self._usage_list)
        n = len(self._usage_list)
        out: dict[str, Any] = {
            "num_calls": n,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "per_call": self._usage_list,
        }
        latencies = [
            u["latency_ms"] for u in self._usage_list
            if u.get("latency_ms") is not None
        ]
        if latencies:
            out["latency_ms"] = {
                "min": min(latencies),
                "max": max(latencies),
                "mean": sum(latencies) / len(latencies),
                "sum": sum(latencies),
            }
        return out
