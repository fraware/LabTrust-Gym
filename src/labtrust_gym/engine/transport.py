"""
Multi-site transport: consignments, DISPATCH_TRANSPORT, TRANSPORT_TICK, RECEIVE_TRANSPORT, CHAIN_OF_CUSTODY_SIGN.

- site_id for zones/devices/specimens (SITE_HUB, SITE_ACUTE).
- Deterministic: transport_time sampled via RNG wrapper; temp_drift bounded.
- Invariants: INV-COC-001 (dispatch must have receive or token), INV-TRANSPORT-001 (temp in band or OVERRIDE token).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml

TRANSPORT_ROUTE_FORBIDDEN = "TRANSPORT_ROUTE_FORBIDDEN"
TRANSPORT_TEMP_EXCURSION = "TRANSPORT_TEMP_EXCURSION"
TRANSPORT_CHAIN_OF_CUSTODY_BROKEN = "TRANSPORT_CHAIN_OF_CUSTODY_BROKEN"


def load_sites_policy(path: Path | str | None = None) -> dict[str, Any]:
    """Load sites_policy.v0.1 YAML. Returns dict with sites, site_graph, routes."""
    if path is None:
        p = Path("policy/sites/sites_policy.v0.1.yaml")
    else:
        p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        return {"sites": [], "site_graph": [], "routes": []}
    try:
        data = load_yaml(p)
    except PolicyLoadError:
        return {"sites": [], "site_graph": [], "routes": []}
    root = data.get("sites_policy")
    if not root:
        return {"sites": [], "site_graph": [], "routes": []}
    return {
        "sites": root.get("sites") or [],
        "site_graph": root.get("site_graph") or [],
        "routes": root.get("routes") or [],
    }


def _route_allowed(policy: dict[str, Any], from_site: str, to_site: str) -> bool:
    """True if policy allows route from_site -> to_site (site_graph enabled)."""
    for edge in policy.get("site_graph") or []:
        if edge.get("from_site") == from_site and edge.get("to_site") == to_site:
            return bool(edge.get("enabled", True))
    return False


def _get_route(policy: dict[str, Any], from_site: str, to_site: str) -> dict[str, Any] | None:
    """Return route config for from_site -> to_site or None."""
    for r in policy.get("routes") or []:
        if r.get("from_site") == from_site and r.get("to_site") == to_site:
            return cast(dict[str, Any] | None, r)
    return None


def _sample_transport_time_s(
    mean_s: int,
    std_s: int,
    rng: Any,
) -> int:
    """Deterministic transport time (mean + bounded noise from RNG)."""
    if std_s <= 0:
        return int(mean_s)
    # Gaussian-like: use uniform around mean for reproducibility
    delta = rng.randint(-min(std_s, mean_s // 2), min(std_s, mean_s // 2))
    return int(max(1, int(mean_s) + delta))


class TransportStore:
    """
    Consignments in transit; dispatch, tick, receive, chain-of-custody.
    INV-COC-001: every dispatch must have receive or CHAIN_OF_CUSTODY_SIGN token.
    INV-TRANSPORT-001: temp in band or OVERRIDE_RISK_ACCEPTANCE.
    """

    def __init__(
        self,
        policy: dict[str, Any] | None = None,
        rng: Any | None = None,
    ) -> None:
        self._policy = policy or {}
        self._rng = rng
        self._consignments: dict[str, dict[str, Any]] = {}
        self._next_consignment_id = 0

    def load_policy(self, policy: dict[str, Any]) -> None:
        self._policy = policy

    def set_rng(self, rng: Any) -> None:
        self._rng = rng

    def dispatch(
        self,
        specimen_ids: list[str],
        origin_site: str,
        dest_site: str,
        now_s: int,
        agent_id: str,
    ) -> tuple[str | None, str | None]:
        """
        DISPATCH_TRANSPORT: create consignment, set expected arrival.
        Returns (consignment_id, reason_code). reason_code TRANSPORT_ROUTE_FORBIDDEN if route not allowed.
        """
        if not _route_allowed(self._policy, origin_site, dest_site):
            return None, TRANSPORT_ROUTE_FORBIDDEN
        route = _get_route(self._policy, origin_site, dest_site)
        if not route:
            return None, TRANSPORT_ROUTE_FORBIDDEN
        mean_s = int(route.get("transport_time_mean_s", 600))
        std_s = int(route.get("transport_time_std_s", 0))
        travel_s = _sample_transport_time_s(mean_s, std_s, self._rng) if self._rng else mean_s
        self._next_consignment_id += 1
        cid = f"CONS_{self._next_consignment_id}"
        self._consignments[cid] = {
            "consignment_id": cid,
            "specimen_ids": list(specimen_ids),
            "origin_site": origin_site,
            "dest_site": dest_site,
            "dispatch_ts": now_s,
            "expected_arrival_ts": now_s + travel_s,
            "current_temp_drift_c": 0.0,
            "temp_band": route.get("temp_band", "AMBIENT_20_25"),
            "temp_drift_max_c": float(route.get("temp_drift_max_c", 2.0)),
            "status": "in_transit",
            "dispatched_by": agent_id,
            "received_ts": None,
            "chain_of_custody_signed": False,
        }
        return cid, None

    def tick(self, now_s: int) -> list[tuple[str, str | None]]:
        """
        TRANSPORT_TICK: advance state; may apply bounded temp drift.
        Returns list of (consignment_id, reason_code) for consignments that had temp excursion (reason_code TRANSPORT_TEMP_EXCURSION).
        """
        excursions: list[tuple[str, str | None]] = []
        for cid, c in list(self._consignments.items()):
            if c.get("status") != "in_transit":
                continue
            max_drift = c.get("temp_drift_max_c", 2.0)
            if self._rng and max_drift > 0:
                delta = (self._rng.random() - 0.5) * 2 * 0.2
                c["current_temp_drift_c"] = c.get("current_temp_drift_c", 0) + delta
                c["current_temp_drift_c"] = max(-max_drift, min(max_drift, c["current_temp_drift_c"]))
            if abs(c.get("current_temp_drift_c", 0)) >= max_drift * 0.99:
                excursions.append((cid, TRANSPORT_TEMP_EXCURSION))
        return excursions

    def receive(
        self,
        consignment_id: str,
        now_s: int,
        agent_id: str,
    ) -> tuple[bool, str | None]:
        """
        RECEIVE_TRANSPORT: mark consignment arrived at destination.
        Returns (ok, reason_code). reason_code TRANSPORT_TEMP_EXCURSION if temp out of band.
        """
        c = self._consignments.get(consignment_id)
        if not c:
            return False, TRANSPORT_CHAIN_OF_CUSTODY_BROKEN
        if c.get("status") != "in_transit":
            return False, TRANSPORT_CHAIN_OF_CUSTODY_BROKEN
        max_drift = c.get("temp_drift_max_c", 2.0)
        if abs(c.get("current_temp_drift_c", 0)) >= max_drift:
            return False, TRANSPORT_TEMP_EXCURSION
        c["status"] = "arrived"
        c["received_ts"] = now_s
        c["received_by"] = agent_id
        return True, None

    def chain_of_custody_sign(
        self,
        consignment_id: str,
        agent_id: str,
    ) -> tuple[bool, str | None]:
        """
        CHAIN_OF_CUSTODY_SIGN: optional dual-approval for handoff anomaly; mark signed.
        Returns (ok, reason_code).
        """
        c = self._consignments.get(consignment_id)
        if not c:
            return False, TRANSPORT_CHAIN_OF_CUSTODY_BROKEN
        c["chain_of_custody_signed"] = True
        c["coc_signed_by"] = agent_id
        return True, None

    def inject_temp_excursion(self, consignment_id: str) -> None:
        """Force temp excursion for consignment (for deterministic golden scenarios)."""
        c = self._consignments.get(consignment_id)
        if c is not None:
            max_drift = c.get("temp_drift_max_c", 2.0)
            c["current_temp_drift_c"] = max_drift

    def get_consignment(self, consignment_id: str) -> dict[str, Any] | None:
        return self._consignments.get(consignment_id)

    def list_in_transit(self) -> list[str]:
        return [cid for cid, c in self._consignments.items() if c.get("status") == "in_transit"]

    def list_consignments_info(self) -> list[dict[str, Any]]:
        """Return list of consignment dicts for obs/query: consignment_id, specimen_ids, expected_arrival_ts, chain_of_custody_signed, status."""
        out: list[dict[str, Any]] = []
        for cid, c in sorted(self._consignments.items()):
            out.append(
                {
                    "consignment_id": cid,
                    "specimen_ids": list(c.get("specimen_ids") or []),
                    "origin_site": c.get("origin_site", ""),
                    "dest_site": c.get("dest_site", ""),
                    "expected_arrival_ts": c.get("expected_arrival_ts"),
                    "chain_of_custody_signed": bool(c.get("chain_of_custody_signed", False)),
                    "status": c.get("status", "in_transit"),
                }
            )
        return out

    def dispatch_has_receive_or_token(self, consignment_id: str) -> bool:
        """True if consignment arrived or has chain_of_custody_signed (INV-COC-001)."""
        c = self._consignments.get(consignment_id)
        if not c:
            return False
        return c.get("status") == "arrived" or c.get("chain_of_custody_signed", False)
