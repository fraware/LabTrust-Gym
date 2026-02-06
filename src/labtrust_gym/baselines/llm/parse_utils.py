"""
Robust JSON parsing for LLM responses when provider does not enforce schema.

- extract_first_json_object(raw): extract first top-level JSON object from text.
  Used when supports_structured_outputs=False (e.g. Ollama, vLLM) so markdown
  or trailing text does not break parsing. Repair loop (PR-15) in agent uses
  this plus ActionProposal validation.
"""

from __future__ import annotations


def extract_first_json_object(raw: str) -> str | None:
    """
    Extract the first top-level JSON object from raw text.

    Handles leading/trailing text and markdown code blocks. Uses balanced
    brace matching; returns the substring that is a single JSON object,
    or None if none found.

    Examples:
        "Here is the result: {\"a\": 1} rest" -> "{\"a\": 1}"
        "```json\n{\"a\": 1}\n```" -> "{\"a\": 1}"
        "no json" -> None
    """
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    quote_char: str | None = None
    i = start
    while i < len(text):
        c = text[i]
        if escape:
            escape = False
            i += 1
            continue
        if c == "\\" and in_string:
            escape = True
            i += 1
            continue
        if in_string:
            if c == quote_char:
                in_string = False
            i += 1
            continue
        if c in ('"', "'"):
            in_string = True
            quote_char = c
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return None
