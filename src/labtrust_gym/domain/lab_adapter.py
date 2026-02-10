"""
Hospital lab domain adapter: maps workflow spec and config to CoreEnv (LabTrustEnvAdapter).

The lab is the reference implementation. The factory ignores the workflow spec for now
and returns CoreEnv(); future extensions can use the spec to configure scale, zones, etc.
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.runner.adapter import LabTrustEnvAdapter


def lab_domain_adapter_factory(
    workflow_spec: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> LabTrustEnvAdapter:
    """
    Return a LabTrustEnvAdapter for the hospital lab domain.

    CoreEnv implements LabTrustEnvAdapter (reset, step, query). The workflow_spec
    and config can be used in future to configure scale, zones, or equipment;
    for v0.1 we ignore them and return a default CoreEnv instance.
    """
    del workflow_spec, config  # unused in v0.1; lab uses policy/ and task config
    return CoreEnv()
