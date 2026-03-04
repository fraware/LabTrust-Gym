"""
CLI output facade: unified, detailed, and visually consistent logging for all labtrust commands.

All user-facing output goes to stderr (per CLI contract); only --version prints to stdout.
Supports verbosity (QUIET, NORMAL, VERBOSE), optional Rich-based rendering with plain fallback,
and progress reporting for long-running commands.
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Verbosity
# ---------------------------------------------------------------------------


class Verbosity(int, Enum):
    """CLI verbosity level; controls what is shown on stderr."""

    QUIET = 0  # Only errors and minimal summary
    NORMAL = 1  # Info, success, warnings, errors
    VERBOSE = 2  # Plus debug, progress detail, tracebacks


def verbosity_from_args(verbose: bool = False, quiet: bool = False) -> Verbosity:
    """Derive verbosity from --verbose and --quiet flags (quiet wins)."""
    if quiet:
        return Verbosity.QUIET
    if verbose:
        return Verbosity.VERBOSE
    return Verbosity.NORMAL


# ---------------------------------------------------------------------------
# Rich detection and console
# ---------------------------------------------------------------------------

_rich_console: Any = None
_rich_available: bool = False


def _init_rich() -> None:
    global _rich_console, _rich_available
    if _rich_console is not None:
        return
    try:
        from rich.console import Console

        _rich_console = Console(file=sys.stderr, force_terminal=None)
        _rich_available = True
    except ImportError:
        _rich_console = None
        _rich_available = False


def is_rich_available() -> bool:
    """Return True if Rich is installed and will be used for output."""
    _init_rich()
    return _rich_available


# ---------------------------------------------------------------------------
# CLI output facade
# ---------------------------------------------------------------------------


class CLIOutput:
    """
    Single entry point for CLI output. Respects verbosity and uses Rich when available.
    All methods write to stderr.
    """

    def __init__(self, verbosity: Verbosity = Verbosity.NORMAL) -> None:
        self._verbosity = verbosity
        _init_rich()

    @property
    def verbosity(self) -> Verbosity:
        return self._verbosity

    def _write(self, message: str, *, strip_markup: bool = False) -> None:
        if _rich_available and not strip_markup:
            _rich_console.print(message, end="")
        else:
            sys.stderr.write(message)
            sys.stderr.flush()

    def _write_line(self, message: str, *, strip_markup: bool = False) -> None:
        if _rich_available and not strip_markup:
            _rich_console.print(message)
        else:
            sys.stderr.write(message + "\n")
            sys.stderr.flush()

    def info(self, message: str, **kwargs: Any) -> None:
        """Show informational message (NORMAL and VERBOSE)."""
        if self._verbosity < Verbosity.NORMAL:
            return
        if _rich_available:
            _rich_console.print(f"[dim]{message}[/]", **kwargs)
        else:
            self._write_line(message)

    def success(self, message: str, **kwargs: Any) -> None:
        """Show success message (NORMAL and VERBOSE)."""
        if self._verbosity < Verbosity.NORMAL:
            return
        if _rich_available:
            _rich_console.print(f"[green]{message}[/]", **kwargs)
        else:
            self._write_line(message)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Show warning (always unless QUIET suppresses non-errors)."""
        if self._verbosity < Verbosity.NORMAL:
            return
        if _rich_available:
            _rich_console.print(f"[yellow]{message}[/]", **kwargs)
        else:
            self._write_line(message)

    def error(self, message: str, **kwargs: Any) -> None:
        """Show error (always shown)."""
        if _rich_available:
            _rich_console.print(f"[red]{message}[/]", **kwargs)
        else:
            self._write_line(message)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Show debug message (VERBOSE only)."""
        if self._verbosity < Verbosity.VERBOSE:
            return
        if _rich_available:
            _rich_console.print(f"[dim]{message}[/]", **kwargs)
        else:
            self._write_line(message)

    def step(self, message: str, **kwargs: Any) -> None:
        """Progress/step message (NORMAL and VERBOSE). Alias for consistent 'step' wording."""
        self.info(message, **kwargs)

    def progress(self, message: str, **kwargs: Any) -> None:
        """Progress message (VERBOSE: per-item; NORMAL: optional summary)."""
        if self._verbosity >= Verbosity.VERBOSE:
            self.info(message, **kwargs)
        # In NORMAL we rely on progress bar or final summary

    def write_plain(self, message: str) -> None:
        """Write raw message to stderr (no styling). Use for contract-stable strings."""
        self._write_line(message, strip_markup=True)

    def table(self, headers: list[str], rows: list[list[str]], title: str | None = None) -> None:
        """Render a table (Rich if available; else plain rows). Only in NORMAL/VERBOSE."""
        if self._verbosity < Verbosity.NORMAL:
            return
        if _rich_available:
            from rich.table import Table

            t = Table(title=title)
            for h in headers:
                t.add_column(h)
            for row in rows:
                t.add_row(*row)
            _rich_console.print(t)
        else:
            if title:
                self._write_line(title)
            self._write_line(" | ".join(headers))
            for row in rows:
                self._write_line(" | ".join(row))

    def panel(self, content: str, title: str | None = None, border_style: str = "dim") -> None:
        """Render a panel (Rich if available). Only in NORMAL/VERBOSE."""
        if self._verbosity < Verbosity.NORMAL:
            return
        if _rich_available:
            from rich.panel import Panel

            _rich_console.print(Panel(content, title=title, border_style=border_style))
        else:
            if title:
                self._write_line(f"--- {title} ---")
            self._write_line(content)

    def print_exception(self, exc: BaseException) -> None:
        """Print exception and traceback (VERBOSE: full; NORMAL: message only)."""
        if self._verbosity >= Verbosity.VERBOSE and _rich_available:
            _rich_console.print_exception(show_locals=False)
        else:
            self.error(f"{type(exc).__name__}: {exc}")


# Global facade instance; set by main() after parsing args.
_console: CLIOutput | None = None


def get_console() -> CLIOutput:
    """Return the global CLI output facade; creates a NORMAL default if not set."""
    global _console
    if _console is None:
        _console = CLIOutput(Verbosity.NORMAL)
    return _console


def set_console(console: CLIOutput) -> None:
    """Set the global CLI output facade (used by main after parsing verbosity)."""
    global _console
    _console = console
