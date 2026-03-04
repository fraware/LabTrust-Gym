"""
Tests for tool execution configuration: missing adapter raises typed error.

No silent no-op; execute_tool_safely(adapter=None) raises
ToolExecutionConfigurationError with remediation and docs link.
"""

from __future__ import annotations

import pytest

from labtrust_gym.tools.execution import (
    ToolExecutionConfigurationError,
    execute_tool_safely,
)


def test_execute_tool_safely_missing_adapter_raises() -> None:
    """adapter=None raises ToolExecutionConfigurationError."""
    with pytest.raises(ToolExecutionConfigurationError) as exc_info:
        execute_tool_safely("read_lims_v1", {"accession_id": "A1"}, adapter=None)
    assert "tool_adapter" in (exc_info.value.remediation or "")
    assert getattr(exc_info.value, "docs_section", None)
