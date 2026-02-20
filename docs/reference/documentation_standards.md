# Documentation standards

This document defines how we write comments and docstrings across the codebase so that everything is clear, consistent, and understandable without jargon.

## Goals

- **Clarity:** Any reader can understand what a module, class, or function does and why it exists.
- **No unexplained jargon:** Use plain language. Define acronyms and domain terms on first use, or link to docs (e.g. "golden scenarios" in `policy/golden/`).
- **Structure:** Each file has a clear purpose; each public API has a short description and, where helpful, parameter/return/exception notes.

## Where to document

| Location | What to add |
|----------|-------------|
| **Module (file)** | A docstring at the top: one or two sentences on what the module does and how it fits in (e.g. "Used by the engine for X" or "Called from the CLI when Y"). |
| **Classes** | A short description of the class role. For non-obvious attributes or lifecycle, add a sentence or two. |
| **Public functions/methods** | What the function does, what the main arguments mean, what it returns, and any important exceptions or side effects. |
| **Complex or non-obvious logic** | Inline comments that explain *why*, not *what* (the code shows what). |

## Style

- **Language:** Prefer simple, direct sentences. Avoid slang and unexplained abbreviations.
- **Length:** Prefer short over long. One good sentence is better than a paragraph of filler.
- **References:** When referring to external concepts (e.g. "golden scenarios", "GS-022"), either explain in one line or point to the doc/schema (e.g. "See `policy/golden/golden_scenarios.v0.1.yaml`").
- **Python docstrings:** Use triple-quoted strings in **Google style** (see below).

## Python docstring format

Use **Google-style** docstrings so MkDocs and readers get a consistent format.

- **Summary:** Every public function and method has a one-line summary (what it does).
- **Args:** List each parameter with type and meaning. Omit only for parameterless functions.
- **Returns:** Describe the return value (and type if non-obvious). For void functions use `Returns: None.`
- **Raises:** Include when the callable can raise documented exceptions (e.g. `ValueError`, `KeyError`).

A single paragraph only (no Args/Returns/Raises) is acceptable for very trivial callables (e.g. a property getter that only returns `self._x`). For all other public APIs, use the full format.

Example:

```python
def apply_policy(env: BaseEnv, agent: str, action_mask: np.ndarray) -> int:
    """Select an action for the agent using the current policy and mask.

    Args:
        env: The environment instance (used for observation).
        agent: Agent identifier.
        action_mask: Boolean mask; only True indices are valid.

    Returns:
        The chosen action index (within the masked set).

    Raises:
        ValueError: If no valid action is available (all mask entries False).
    """
```

## Code style

- **Line length:** Maximum 120 characters per line. New and edited code must comply; `ruff check` (E501) will enforce once the existing backlog is cleared. Break long lines with parentheses or implied continuation; avoid backslash continuation where possible.

## What to avoid

- **Jargon without definition:** Do not assume the reader knows "RBAC", "QC", "MARL", "SOTA", "invariant", "reason_code", etc. without at least a one-line explanation or a link.
- **Commenting the obvious:** Do not comment every line. Comment decisions, constraints, and non-obvious behavior.
- **Outdated comments:** When changing behavior, update or remove the related comments.

## Golden scenarios and scenario IDs

The engine and many tests refer to **golden scenarios** (correctness specifications) and **scenario IDs** (e.g. GS-022, GS-010). These are defined in `policy/golden/golden_scenarios.v0.1.yaml`. In docstrings, you may either:

- Say "Supports golden scenario GS-022 (audit hash chain and forensic freeze)."
- Or "Supports the audit hash chain and forensic freeze behavior; see golden scenario GS-022 in `policy/golden/`."

Prefer the second form when the audience may not know what GS-022 is.

## Checklist for new or edited code

- [ ] Module has a top-level docstring.
- [ ] Public classes and functions have docstrings in Google style (summary; Args/Returns/Raises where applicable).
- [ ] Acronyms and domain terms are explained or linked.
- [ ] Tricky logic has a brief "why" comment.
- [ ] No redundant or misleading comments.
- [ ] Lines do not exceed 120 characters (ruff E501).
