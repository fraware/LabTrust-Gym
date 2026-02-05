"""
Securitization packet: coverage and deps_inventory generation is deterministic.
Same policy inputs yield same coverage.json and deps_inventory.json content.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.securitization import (
    _build_coverage_data,
    emit_securitization_packet,
    write_coverage,
    write_deps_inventory,
    write_reason_codes_md,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_coverage_build_deterministic() -> None:
    """_build_coverage_data returns same structure for same policy root."""
    root = _repo_root()
    c1 = _build_coverage_data(root)
    c2 = _build_coverage_data(root)
    assert c1.get("version") == c2.get("version") == "0.1"
    assert c1.get("risk_to_controls") == c2.get("risk_to_controls")
    assert c1.get("control_to_tests") == c2.get("control_to_tests")


def test_write_coverage_deterministic() -> None:
    """Writing coverage twice produces identical coverage.json (and coverage.md)."""
    root = _repo_root()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sec"
        write_coverage(root, out)
        path_json = out / "SECURITY" / "coverage.json"
        path_md = out / "SECURITY" / "coverage.md"
        assert path_json.exists()
        assert path_md.exists()
        content1 = path_json.read_text(encoding="utf-8")
        write_coverage(root, out)
        content2 = path_json.read_text(encoding="utf-8")
        assert content1 == content2
        assert json.loads(content1).get("version") == "0.1"


def test_write_deps_inventory_deterministic() -> None:
    """Writing deps_inventory twice with same policy yields same fingerprint fields."""
    root = _repo_root()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sec"
        write_deps_inventory(root, out)
        path = out / "SECURITY" / "deps_inventory.json"
        assert path.exists()
        d1 = json.loads(path.read_text(encoding="utf-8"))
        write_deps_inventory(root, out)
        d2 = json.loads(path.read_text(encoding="utf-8"))
        assert d1.get("version") == d2.get("version") == "0.1"
        if d1.get("tool_registry") and d2.get("tool_registry"):
            assert d1["tool_registry"].get("fingerprint") == d2["tool_registry"].get(
                "fingerprint"
            )


def test_emit_securitization_packet_creates_all_files() -> None:
    """emit_securitization_packet creates coverage.json, coverage.md, reason_codes.md, deps_inventory.json, deps_inventory_runtime.json."""
    root = _repo_root()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sec"
        emit_securitization_packet(root, out)
        sec = out / "SECURITY"
        assert (sec / "coverage.json").exists()
        assert (sec / "coverage.md").exists()
        assert (sec / "reason_codes.md").exists()
        assert (sec / "deps_inventory.json").exists()
        assert (sec / "deps_inventory_runtime.json").exists()
