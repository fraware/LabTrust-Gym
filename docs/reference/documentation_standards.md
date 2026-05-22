# Documentation standards

This document defines how we write comments, docstrings, and published documentation so that every page reads clearly, consistently, and without unexplained jargon.

## Goals

- **Clarity.** Any reader can understand what a module, class, function, or workflow does and how it fits the wider system.
- **Defined terms.** Use plain language. Define acronyms and domain terms on first use, or link to the [glossary](glossary.md) or policy files.
- **Structure.** Each file states its purpose up front; each public API includes a short description and, where helpful, parameter, return, and exception notes.

## Documentation voice (published pages)

Apply these rules to all Markdown under `docs/` and to user-facing README sections.

| Rule | Guidance |
|------|----------|
| **Affirmative phrasing** | State what the system does. Rewrite negation-heavy contrasts (for example “not X but Y”) into direct positive statements. |
| **Sentence length** | Prefer full, well-structured sentences over telegraphic fragments. Combine related ideas when a single flowing sentence reads better. |
| **No “rather than”** | Choose one path explicitly (“use throughput_sla when throughput is the primary metric”) instead of contrasting with a rejected alternative. |
| **No colon-led sentences** | Avoid “Label: explanation” in running text. Use a complete sentence (“The trace model is described in …”) or a table row. |
| **Banned terms** | Do not use *prose*, *brittle*, *quiet*, or *survive* in documentation text. Refer to the `-q` flag or “minimal output” instead of “quiet mode”. |
| **Repeated pivots** | Limit chains such as “This is why …”; move the explanation into the preceding paragraph. |

Code blocks, CLI flags, JSON field names, and schema identifiers may keep their exact spelling even when they contain words from the banned list.

## Where to document

| Location | What to add |
|----------|-------------|
| **Module (file)** | A docstring at the top with one or two sentences on what the module does and how it fits in (for example “Used by the engine for X” or “Called from the CLI when Y”). |
| **Classes** | A short description of the class role. For non-obvious attributes or lifecycle, add a sentence or two. |
| **Public functions/methods** | What the function does, what the main arguments mean, what it returns, and any important exceptions or side effects. |
| **Complex or non-obvious logic** | Inline comments that explain intent and constraints; the code already shows the mechanics. |

## Style

- **Language.** Prefer simple, direct sentences. Avoid slang and unexplained abbreviations.
- **Length.** Prefer complete sentences over bullet-only pages when the topic needs narrative context; use tables and lists for reference material.
- **References.** When referring to external concepts (for example “golden scenarios”, “GS-022”), explain in one line or point to the doc or schema (for example `policy/golden/golden_scenarios.v0.1.yaml`).
- **Python docstrings.** Use triple-quoted strings in **Google style** (see below).

## Python docstring format

Use **Google-style** docstrings so MkDocs and readers get a consistent format.

- **Summary.** Every public function and method has a one-line summary (what it does).
- **Args.** List each parameter with type and meaning. Omit only for parameterless functions.
- **Returns.** Describe the return value (and type if non-obvious). For void functions use `Returns: None.`
- **Raises.** Include when the callable can raise documented exceptions (for example `ValueError`, `KeyError`).

A single paragraph only (no Args/Returns/Raises) is acceptable for very trivial callables (for example a property getter that only returns `self._x`). For all other public APIs, use the full format.

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

- **Line length.** Maximum 120 characters per line. New and edited code must comply; `ruff check` (E501) will enforce once the existing backlog is cleared. Break long lines with parentheses or implied continuation; avoid backslash continuation where possible.

## What to avoid

- **Jargon without definition.** Do not assume the reader knows “RBAC”, “QC”, “MARL”, “SOTA”, “invariant”, “reason_code”, and similar terms without at least a one-line explanation or a link.
- **Commenting the obvious.** Comment decisions, constraints, and non-obvious behavior instead of restating each line.
- **Outdated comments.** When changing behavior, update or remove the related comments.

## Golden scenarios and scenario IDs

The engine and many tests refer to **golden scenarios** (correctness specifications) and **scenario IDs** (for example GS-022, GS-010). These are defined in `policy/golden/golden_scenarios.v0.1.yaml`. In docstrings, you may either:

- Say “Supports golden scenario GS-022 (audit hash chain and forensic freeze).”
- Or “Supports the audit hash chain and forensic freeze behavior; see golden scenario GS-022 in `policy/golden/`.”

Prefer the second form when the audience may not know what GS-022 is.

## Checklist for new or edited code

- [ ] Module has a top-level docstring.
- [ ] Public classes and functions have docstrings in Google style (summary; Args/Returns/Raises where applicable).
- [ ] Acronyms and domain terms are explained or linked.
- [ ] Tricky logic has a brief intent comment.
- [ ] No redundant or misleading comments.
- [ ] Lines do not exceed 120 characters (ruff E501).
- [ ] Published Markdown follows the documentation voice rules above.
