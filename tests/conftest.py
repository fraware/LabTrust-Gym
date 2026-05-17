"""
Pytest configuration and shared fixtures.

- block_network_when_offline: when pipeline_mode != llm_live, blocks socket connect
  for the duration of the test. Use for tests that must guarantee no outbound calls.
- registers custom markers (belt-and-suspenders with pyproject.toml)
- skips tests that need PettingZoo when pip install -e ".[env]" was not used
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from tests.network_guard import network_guard_when_offline

_ENV_INSTALL_HINT = 'pip install -e ".[env]"'

_MARKERS = (
    ("metamorphic", "metamorphic property tests (deterministic relations)."),
    ("determinism", "failure physics / determinism tests (seeded)."),
    ("live", "integration tests that call live APIs (require OPENAI_API_KEY, LABTRUST_RUN_LLM_LIVE=1)."),
    ("security", "security fuzz and property tests (injection points, no action outside allowed)."),
    (
        "security_fuzz_stress",
        "hypothesis-based security fuzz with higher max_examples (nightly); use --hypothesis-max-examples=500.",
    ),
    ("slow", "long-running tests (golden suite, package-release, heavy CLI); exclude with -m 'not slow'."),
    ("pcs", "proof-carrying science (PCS) artifact and qc-release demo tests."),
)


def pytest_configure(config: pytest.Config) -> None:
    for name, description in _MARKERS:
        config.addinivalue_line("markers", f"{name}: {description}")


def _import_error_should_skip(exc: BaseException) -> bool:
    if not isinstance(exc, ImportError):
        return False
    msg = str(exc)
    return (
        _ENV_INSTALL_HINT in msg
        or "pettingzoo" in msg.lower()
        or "gymnasium" in msg.lower()
        or "LabTrustParallelEnv" in msg
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> None:
    """Turn missing [env] ImportErrors into skips instead of failures."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed and call.excinfo is not None:
        if _import_error_should_skip(call.excinfo.value):
            report.outcome = "skipped"
            report.longrepr = str(call.excinfo.value)
    outcome.force_result(report)


@pytest.fixture
def block_network_when_offline() -> Generator[None, None, None]:
    """
    When pipeline_mode is not llm_live, block outbound socket connect for this test.
    Restores socket on teardown. Use for deterministic/llm_offline tests that must
    never perform network calls.
    """
    with network_guard_when_offline():
        yield
