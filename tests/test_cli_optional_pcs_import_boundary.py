"""Regression: core CLI initialization must not import the optional PCS package."""

from __future__ import annotations

import subprocess
import sys


def test_cli_help_works_without_pcs_core() -> None:
    """The default CLI command registry is available with only base dependencies."""
    script = """
import sys
# Block importing pcs_core even if a developer installed the PCS optional extra.
sys.modules["pcs_core"] = None
from labtrust_gym.cli.main import main
sys.argv = ["labtrust", "--help"]
main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        timeout=40,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
