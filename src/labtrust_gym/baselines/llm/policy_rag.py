"""
RAG over policy documents for LLM context (SOTA).

- Indexes policy YAML/JSON under policy/ as text chunks.
- Retrieval: keyword/section-based by default (no embedding dependency);
  optional embedding when LABTRUST_RAG_EMBEDDINGS=1.
- Injects top-k relevant excerpts for allowed_actions and constraints.
- Used when context.use_rag=True; opt-in.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Default number of chunks to inject.
DEFAULT_TOP_K = 3
# Max chars per chunk in the prompt.
MAX_CHUNK_CHARS = 600


def _get_repo_root() -> Path:
    try:
        from labtrust_gym.config import get_repo_root

        return Path(get_repo_root())
    except Exception:
        return Path(__file__).resolve().parent.parent.parent.parent.parent


def _chunk_file(path: Path, content: str, source_id: str) -> list[tuple[str, str]]:
    """
    Split file content into (chunk_id, text) pairs.
    Prefer YAML key-based splitting; fallback to line-based blocks.
    """
    chunks: list[tuple[str, str]] = []
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml

            data = yaml.safe_load(content)
            if isinstance(data, dict):
                for key, val in data.items():
                    head = f"[{source_id}] {key}"
                    if isinstance(val, (dict, list)):
                        body = json.dumps(val, sort_keys=True)[:MAX_CHUNK_CHARS]
                    else:
                        body = str(val)[:MAX_CHUNK_CHARS]
                    chunks.append((f"{source_id}:{key}", f"{head}\n{body}"))
                return chunks
        except Exception:
            pass
    lines = content.splitlines()
    block: list[str] = []
    block_start = 0
    for i, line in enumerate(lines):
        block.append(line)
        if len("\n".join(block)) >= 400 or i == len(lines) - 1:
            text = "\n".join(block)[:MAX_CHUNK_CHARS]
            chunks.append((f"{source_id}:L{block_start}", text))
            block = []
            block_start = i + 1
    if block:
        text = "\n".join(block)[:MAX_CHUNK_CHARS]
        chunks.append((f"{source_id}:L{block_start}", text))
    return chunks


def load_policy_chunks(
    repo_root: Path | None = None,
    include_dirs: list[str] | None = None,
) -> list[tuple[str, str]]:
    """
    Load policy directory into list of (chunk_id, text). By default indexes
    policy/rbac, policy/tokens, policy/invariants, policy/llm, policy/zones.
    """
    root = repo_root or _get_repo_root()
    if include_dirs is None:
        include_dirs = [
            "policy/rbac",
            "policy/tokens",
            "policy/invariants",
            "policy/llm",
            "policy/zones",
            "policy/critical",
        ]
    all_chunks: list[tuple[str, str]] = []
    for dir_name in include_dirs:
        dir_path = root / dir_name
        if not dir_path.is_dir():
            continue
        for path in sorted(dir_path.rglob("*.yaml")):
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            source_id = path.relative_to(root).as_posix().replace("/", "_")
            all_chunks.extend(_chunk_file(path, content, source_id))
        for path in sorted(dir_path.rglob("*.json")):
            if "schema" in path.name.lower():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            source_id = path.relative_to(root).as_posix().replace("/", "_")
            all_chunks.extend(_chunk_file(path, content, source_id))
    return all_chunks


def _query_terms(state_summary: dict[str, Any], allowed_actions: list[str]) -> set[str]:
    """Extract search terms from state and allowed_actions."""
    terms: set[str] = set()
    for a in allowed_actions or []:
        terms.add(str(a).upper())
    if isinstance(state_summary, dict):
        for key, val in state_summary.items():
            terms.add(str(key).lower())
            if isinstance(val, dict):
                terms.update(str(k).lower() for k in val.keys())
            elif isinstance(val, list):
                for item in val[:5]:
                    if isinstance(item, dict):
                        terms.update(str(k).lower() for k in item.keys())
                    else:
                        terms.add(str(item).upper()[:50])
            elif isinstance(val, str):
                for word in re.findall(r"[A-Za-z0-9_]+", val):
                    if len(word) > 2:
                        terms.add(word)
    return terms


def _score_chunk(chunk_text: str, terms: set[str]) -> int:
    """Simple term-overlap score (case-insensitive)."""
    lower = chunk_text.lower()
    return sum(1 for t in terms if t.lower() in lower or t.upper() in chunk_text)


def retrieve(
    state_summary: dict[str, Any],
    allowed_actions: list[str],
    chunks: list[tuple[str, str]],
    top_k: int = DEFAULT_TOP_K,
) -> list[tuple[str, str]]:
    """
    Return top-k (chunk_id, text) by relevance to state_summary and
    allowed_actions. Uses keyword overlap; no embeddings required.
    """
    terms = _query_terms(state_summary, allowed_actions)
    if not terms or not chunks:
        return chunks[:top_k]
    scored = [((c, text), _score_chunk(text, terms)) for c, text in chunks]
    scored.sort(key=lambda x: -x[1])
    return [pair for (pair, _) in scored[:top_k]]


# Module-level cache for chunks (avoid re-reading files every call).
_chunks_cache: list[tuple[str, str]] | None = None


def get_cached_chunks(repo_root: Path | None = None) -> list[tuple[str, str]]:
    """Return cached policy chunks (load once per process)."""
    global _chunks_cache
    if _chunks_cache is None:
        _chunks_cache = load_policy_chunks(repo_root=repo_root)
    return _chunks_cache


def build_rag_context(
    state_summary: dict[str, Any],
    allowed_actions: list[str],
    repo_root: Path | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> str:
    """
    Retrieve top-k policy chunks and format as one string for prompt injection.
    """
    chunks = get_cached_chunks(repo_root=repo_root)
    selected = retrieve(state_summary, allowed_actions, chunks, top_k=top_k)
    if not selected:
        return ""
    lines = ["--- Relevant policy excerpts ---"]
    for chunk_id, text in selected:
        lines.append(f"\n[{chunk_id}]\n{text}")
    lines.append("\n--- End policy excerpts ---\n")
    return "\n".join(lines)
