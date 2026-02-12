"""
Few-shot example loading and formatting for LLM prompts (SOTA).

- Loads examples from policy/llm/few_shot_examples.v0.1.yaml (or equivalent).
- Formats as user/assistant message pairs for injection into the prompt.
- Cap on total characters/tokens to control context size.
- Used when context.use_few_shot=True; opt-in to avoid changing default behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Approximate max characters for few-shot block (conservative token proxy).
DEFAULT_FEW_SHOT_MAX_CHARS = 1200


def _get_repo_root() -> Path:
    """Resolve repo root for policy paths."""
    try:
        from labtrust_gym.config import get_repo_root
        return Path(get_repo_root())
    except Exception:
        return Path(__file__).resolve().parent.parent.parent.parent.parent


def load_few_shot_examples(
    repo_root: Path | None = None,
    path_segment: str = "policy/llm/few_shot_examples.v0.1.yaml",
) -> list[dict[str, Any]]:
    """
    Load few-shot examples from YAML. Returns list of dicts with keys such as
    user_snippet, assistant_snippet (or state_summary + action_proposal).
    Returns [] if file missing or invalid.
    """
    root = repo_root or _get_repo_root()
    path = root / path_segment
    if not path.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    examples = data.get("examples")
    if not isinstance(examples, list):
        return []
    out: list[dict[str, Any]] = []
    for ex in examples:
        if not isinstance(ex, dict):
            continue
        out.append(ex)
    return out


def _example_to_user_assistant_pair(
    ex: dict[str, Any],
) -> tuple[str, str] | None:
    """
    Convert one example to (user_content, assistant_content).
    Supports user_snippet+assistant_snippet or state_summary+action_proposal.
    """
    user_snippet = ex.get("user_snippet")
    assistant_snippet = ex.get("assistant_snippet")
    if user_snippet is not None and assistant_snippet is not None:
        return (str(user_snippet).strip(), str(assistant_snippet).strip())
    state = ex.get("state_summary")
    action = ex.get("action_proposal")
    if isinstance(state, dict) and isinstance(action, dict):
        user_content = (
            "STATE_SUMMARY_JSON:\n"
            + json.dumps(state, sort_keys=True)
            + "\n\nReturn a single ActionProposal JSON."
        )
        assistant_content = json.dumps(action, sort_keys=True)
        return (user_content, assistant_content)
    return None


def build_few_shot_block(
    examples: list[dict[str, Any]],
    max_chars: int = DEFAULT_FEW_SHOT_MAX_CHARS,
) -> str:
    """
    Build a text block of few-shot User/Assistant pairs for the prompt.
    Stops when adding the next pair would exceed max_chars.
    """
    if not examples:
        return ""
    parts: list[str] = []
    total = 0
    for ex in examples:
        pair = _example_to_user_assistant_pair(ex)
        if pair is None:
            continue
        user_c, assistant_c = pair
        block = f"User:\n{user_c}\n\nAssistant:\n{assistant_c}\n\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    if not parts:
        return ""
    head = "--- Few-shot examples ---\n\n"
    tail = "--- End few-shot ---\n\n"
    return head + "".join(parts) + tail


def get_few_shot_block_from_policy(
    repo_root: Path | None = None,
    max_chars: int = DEFAULT_FEW_SHOT_MAX_CHARS,
) -> str:
    """
    Load examples from policy and return formatted few-shot block.
    One-line helper for backends/context.
    """
    examples = load_few_shot_examples(repo_root=repo_root)
    return build_few_shot_block(examples, max_chars=max_chars)
