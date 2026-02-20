# Code style and lint

This document explains the project's lint rules (Ruff) and the naming exceptions that are configured in `pyproject.toml`. Use it when adding or changing code, or when deciding whether a new name should follow an exception.

## Lint configuration

- **Ruff** is used for format (`ruff format`) and lint (`ruff check`). Both run in CI.
- **Line length:** 120 characters. See [Documentation standards](documentation_standards.md#code-style) for details; E501 is phased in.
- **Naming:** We follow PEP 8 naming in general. The following Ruff rules are **ignored** for specific, documented reasons. Do not add new uses of these patterns unless they fall under the same rationale.

## Ignored naming rules (and why)

These rule codes come from the [pep8-naming](https://docs.astral.sh/ruff/rules/#pep8-naming-n) set. The canonical list is in `pyproject.toml` under `[tool.ruff.lint]` → `ignore`; this section explains each so the naming system is reusable and consistent.

Benchmark task classes use explicit, standalone CapWords names (e.g. `ThroughputSla`, `StatInsertionUnderLoad`, `CoordinationScale`) and are not exempt from N801; see `labtrust_gym.benchmarks.tasks`.

### N802 — invalid-function-name

**Rule:** Function and method names should be lowercase, with words separated by underscores (e.g. `do_get`, not `do_GET`).

**Why we ignore:** The standard library `http.server.BaseHTTPRequestHandler` requires methods named exactly `do_GET`, `do_POST`, `do_HEAD`, etc. These are the hook names the HTTP server calls. We use them in `labtrust_gym.online.server` for the online serve endpoint; renaming would break the handler protocol.

**When to use:** Only for HTTP handler methods that override `BaseHTTPRequestHandler` (e.g. `do_GET`, `do_POST`). All other functions and methods must use lowercase with underscores.

**Ruff docs:** [invalid-function-name (N802)](https://docs.astral.sh/ruff/rules/invalid-function-name/).

---

### N806 — non-lowercase-variable-in-function

**Rule:** Variable names inside functions should be lowercase (PEP 8). UPPER_CASE is reserved for module-level constants.

**Why we ignore:** In some functions we use UPPER_CASE names for values that are constant-like within the function scope (e.g. sets or tuples of allowed values used only in that function). Treating them as “constants in small scope” improves readability and matches existing usage. We do not allow UPPER_CASE for ordinary mutable variables inside functions.

**When to use:** Only for names that are effectively constant within the function (e.g. a frozenset or tuple of allowed keys, or a single constant value). Prefer module-level constants or lowercase names when possible. Do not use UPPER_CASE for loop variables, accumulators, or other mutable state.

**Ruff docs:** [non-lowercase-variable-in-function (N806)](https://docs.astral.sh/ruff/rules/non-lowercase-variable-in-function/).

---

## Summary

| Code  | Rule name                          | Allowed use in this repo                                    |
|-------|------------------------------------|-------------------------------------------------------------|
| N802  | invalid-function-name              | Stdlib HTTP handler methods: `do_GET`, `do_POST`, etc. only. |
| N806  | non-lowercase-variable-in-function | Constant-like names inside a function (sets/tuples/values).  |

Adding a new exception should follow the same rationale and be documented here and in `pyproject.toml` with a short comment.
