"""
Test harness: block outbound sockets/HTTP when pipeline_mode != llm_live.

Use in tests to guarantee deterministic/offline pipelines never perform
network calls. Install before running quick-eval, reproduce, or any
benchmark with pipeline_mode in (deterministic, llm_offline); assert
no RuntimeError and that logs contain "network disabled".

Usage:
  with network_guard_when_offline():
      run_quick_eval(...)  # or run_reproduce, run_benchmark, etc.
  # or: restore = install_network_block(); ...; restore()
"""

from __future__ import annotations

import contextlib
import socket
from typing import Callable, Generator

# Message raised when a blocked connect is attempted (for assertions).
NETWORK_BLOCKED_MSG = "Network is blocked for tests when pipeline_mode != llm_live."


def _blocking_socket_factory(original_socket: type) -> type:
    """Build a socket class that raises on connect/connect_ex."""

    class BlockingSocket(original_socket):
        def connect(self, address: tuple) -> None:
            raise RuntimeError(NETWORK_BLOCKED_MSG)

        def connect_ex(self, address: tuple) -> int:
            raise RuntimeError(NETWORK_BLOCKED_MSG)

    return BlockingSocket


def install_network_block() -> Callable[[], None]:
    """
    Monkeypatch socket.socket so connect/connect_ex raise RuntimeError.
    Use when pipeline_mode is deterministic or llm_offline to fail fast on
    any outbound attempt. Returns a restore callback (call once to restore).
    """
    orig = socket.socket
    BlockingSocket = _blocking_socket_factory(orig)
    socket.socket = BlockingSocket  # type: ignore[assignment]

    def restore() -> None:
        socket.socket = orig  # type: ignore[assignment]

    return restore


def install_network_block_if_offline() -> Callable[[], None]:
    """
    Install network block only when pipeline_mode != llm_live.
    Returns restore callback (no-op if block was not installed).
    """
    try:
        from labtrust_gym.pipeline import get_pipeline_mode
    except Exception:
        return install_network_block()
    if get_pipeline_mode() == "llm_live":
        return lambda: None
    return install_network_block()


@contextlib.contextmanager
def network_guard_when_offline() -> Generator[None, None, None]:
    """
    When pipeline_mode != llm_live, block socket connect for the duration.
    Restores original socket on exit.
    """
    restore = install_network_block_if_offline()
    try:
        yield
    finally:
        restore()
