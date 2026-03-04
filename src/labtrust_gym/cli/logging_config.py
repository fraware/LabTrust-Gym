"""
Central logging configuration for CLI runs.

Attaches a single handler to the labtrust_gym logger based on verbosity and Rich availability.
Library code continues to use logging.getLogger(__name__); this module configures how those
messages are rendered when running from the CLI.
"""

from __future__ import annotations

import logging
import sys

from labtrust_gym.cli.console import Verbosity, is_rich_available


def configure_cli_logging(verbosity: Verbosity) -> None:
    """
    Configure logging for labtrust_gym when running from CLI.
    Call once after parsing verbosity (e.g. in main()).
    """
    root = logging.getLogger("labtrust_gym")
    # Avoid adding duplicate handlers on repeated config (e.g. tests).
    if root.handlers:
        return

    if verbosity == Verbosity.QUIET:
        level = logging.WARNING
    elif verbosity == Verbosity.VERBOSE:
        level = logging.DEBUG
    else:
        level = logging.INFO

    root.setLevel(level)

    if is_rich_available():
        try:
            from rich.console import Console
            from rich.logging import RichHandler

            handler = RichHandler(
                console=Console(stderr=True),
                show_path=False,
                show_time=verbosity == Verbosity.VERBOSE,
                rich_tracebacks=verbosity == Verbosity.VERBOSE,
            )
        except Exception:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    handler.setLevel(level)
    root.addHandler(handler)

    # Optionally reduce noise from third-party loggers unless VERBOSE
    if verbosity != Verbosity.VERBOSE:
        for name in ("urllib3", "openai", "httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)
