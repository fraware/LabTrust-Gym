"""
Pytest configuration and shared fixtures.

- block_network_when_offline: when pipeline_mode != llm_live, blocks socket connect
  for the duration of the test. Use for tests that must guarantee no outbound calls.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from tests.network_guard import network_guard_when_offline


@pytest.fixture
def block_network_when_offline() -> Generator[None, None, None]:
    """
    When pipeline_mode is not llm_live, block outbound socket connect for this test.
    Restores socket on teardown. Use for deterministic/llm_offline tests that must
    never perform network calls.
    """
    with network_guard_when_offline():
        yield
