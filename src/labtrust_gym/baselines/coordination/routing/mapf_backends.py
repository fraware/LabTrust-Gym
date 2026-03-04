"""
MAPF/TAPF router backend ladder: whca (default), cbs, ecbs, lns, rhcr.
WHCA is always available; CBS/ECBS/LNS/RHCR require optional [mapf] and fall back to WHCA.
"""

from __future__ import annotations

from typing import Any


def make_router(
    backend: str,
    horizon: int = 10,
    **kwargs: Any,
) -> Any:
    """
    Create a Router for the given backend.
    Supported: whca (default), cbs, ecbs, lns, rhcr.
    When backend is cbs/ecbs/lns/rhcr and [mapf] not installed, returns WHCARouter.
    """
    from labtrust_gym.baselines.coordination.kernel_components import WHCARouter

    normalized = (backend or "whca").strip().lower()
    if normalized == "whca":
        return WHCARouter(horizon=horizon)

    if normalized in ("cbs", "ecbs", "lns", "rhcr"):
        try:
            return _make_optional_backend(normalized, horizon=horizon, **kwargs)
        except ImportError:
            pass
        return WHCARouter(horizon=horizon)

    return WHCARouter(horizon=horizon)


def _make_optional_backend(
    backend: str,
    horizon: int = 10,
    **kwargs: Any,
) -> Any:
    """CBS/ECBS/LNS/RHCR when [mapf] installed. Raises ImportError otherwise."""
    raise ImportError(f"Router backend {backend!r} requires [mapf]; use pip install -e '.[mapf]'")
