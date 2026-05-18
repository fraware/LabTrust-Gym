"""Registry of PCS demonstration workflows."""

from __future__ import annotations

from labtrust_gym.pcs.workflows.base import PcsWorkflow
from labtrust_gym.pcs.workflows.qc_release import QcReleaseWorkflow

_DEFAULT_WORKFLOW_ID = "qc_release"

_REGISTRY: dict[str, type[PcsWorkflow]] = {
    "qc_release": QcReleaseWorkflow,
}

# property_id and demo aliases for CLI / gallery
_WORKFLOW_ALIASES: dict[str, str] = {
    "hospital_lab.qc_release": "qc_release",
    "labtrust.qc_release_v0.1": "qc_release",
    "qc-release": "qc_release",
}


def registered_workflow_ids() -> tuple[str, ...]:
    return tuple(_REGISTRY.keys())


def resolve_workflow_id(key: str) -> str:
    """Map workflow id, property id, or demo name to a registered workflow id."""
    if key in _REGISTRY:
        return key
    if key in _WORKFLOW_ALIASES:
        return _WORKFLOW_ALIASES[key]
    raise ValueError(
        f"unknown PCS workflow {key!r}; registered: {list(_REGISTRY)}; "
        f"aliases: {list(_WORKFLOW_ALIASES)}"
    )


def get_workflow(workflow_id: str | None = None, *, profile_path: Path | None = None, **kwargs) -> PcsWorkflow:
    """Instantiate a workflow by id (default: qc_release)."""
    wid = resolve_workflow_id(workflow_id or _DEFAULT_WORKFLOW_ID)
    return _REGISTRY[wid](profile_path=profile_path, **kwargs)


def get_workflow_by_key(key: str, **kwargs) -> PcsWorkflow:
    """Instantiate by workflow id, property id (``hospital_lab.qc_release``), or demo name."""
    return get_workflow(resolve_workflow_id(key), **kwargs)


def default_workflow(**kwargs) -> PcsWorkflow:
    return get_workflow(_DEFAULT_WORKFLOW_ID, **kwargs)
