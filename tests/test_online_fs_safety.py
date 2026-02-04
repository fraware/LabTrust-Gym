"""
B008: Filesystem safety for online and artifact paths.

- Path traversal is blocked (.., absolute, drive letters).
- resolve_within_base keeps paths under base dir.
- get_runs_dir respects LABTRUST_RUNS_DIR.
- assert_under_runs_dir raises when path escapes.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from labtrust_gym.security.fs_safety import (
    assert_under_runs_dir,
    get_runs_dir,
    is_safe_filename_component,
    resolve_within_base,
)


def test_resolve_within_base_allows_relative() -> None:
    """Valid relative path under base is returned."""
    base = Path(tempfile.gettempdir()).resolve()
    got = resolve_within_base(base, "run_1")
    assert got is not None
    assert got == base / "run_1"
    got2 = resolve_within_base(base, "run_1/logs")
    assert got2 is not None
    assert got2 == base / "run_1" / "logs"


def test_resolve_within_base_rejects_traversal() -> None:
    """Path with .. escapes and returns None."""
    base = Path(tempfile.gettempdir()).resolve()
    assert resolve_within_base(base, "..") is None
    assert resolve_within_base(base, "run/../etc") is None
    assert resolve_within_base(base, "../other") is None


def test_resolve_within_base_rejects_absolute() -> None:
    """Absolute-looking or drive path is rejected."""
    base = Path(tempfile.gettempdir()).resolve()
    assert resolve_within_base(base, "/etc/passwd") is None
    if os.name == "nt":
        assert resolve_within_base(base, "C:\\Windows") is None


def test_is_safe_filename_component() -> None:
    """Safe and unsafe components are detected."""
    assert is_safe_filename_component("run_1") is True
    assert is_safe_filename_component("") is False
    assert is_safe_filename_component(".") is False
    assert is_safe_filename_component("..") is False
    assert is_safe_filename_component("a/b") is False
    assert is_safe_filename_component("a\\b") is False


def test_get_runs_dir_default() -> None:
    """Without env, get_runs_dir returns cwd."""
    with pytest.MonkeyPatch().context() as m:
        m.delenv("LABTRUST_RUNS_DIR", raising=False)
        r = get_runs_dir()
        assert r == Path.cwd()


def test_get_runs_dir_from_env() -> None:
    """LABTRUST_RUNS_DIR is used when set."""
    with tempfile.TemporaryDirectory() as td:
        with pytest.MonkeyPatch().context() as m:
            m.setenv("LABTRUST_RUNS_DIR", td)
            r = get_runs_dir()
            assert r.resolve() == Path(td).resolve()


def test_get_runs_dir_relative_resolved() -> None:
    """Relative LABTRUST_RUNS_DIR is resolved against cwd."""
    with pytest.MonkeyPatch().context() as m:
        m.setenv("LABTRUST_RUNS_DIR", "labtrust_runs")
        r = get_runs_dir()
        assert r == (Path.cwd() / "labtrust_runs").resolve()


def test_assert_under_runs_dir_ok() -> None:
    """Path under runs dir does not raise."""
    with tempfile.TemporaryDirectory() as td:
        with pytest.MonkeyPatch().context() as m:
            m.setenv("LABTRUST_RUNS_DIR", td)
            assert_under_runs_dir(Path(td) / "run_1")
            assert_under_runs_dir(Path(td) / "run_1" / "logs")


def test_assert_under_runs_dir_raises() -> None:
    """Path outside runs dir raises ValueError."""
    with tempfile.TemporaryDirectory() as td:
        with pytest.MonkeyPatch().context() as m:
            m.setenv("LABTRUST_RUNS_DIR", td)
            with pytest.raises(ValueError, match="not under"):
                assert_under_runs_dir(Path("/tmp/other"))
            with pytest.raises(ValueError, match="not under"):
                assert_under_runs_dir(Path(td).parent)
