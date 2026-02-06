"""
Reservation table: (time_step, node) -> agent_id for collision-free planning.
Bounded horizon; one agent per (t, node) by default (INV-ROUTE-001).
"""

from __future__ import annotations


class ReservationTable:
    """
    (t, node) -> agent_id. At most one agent per (t, node) for INV-ROUTE-001.
    Bounded to t in [0, max_t] to scale to many agents.
    """

    __slots__ = ("_table", "_by_agent", "_max_t")

    def __init__(self, max_t: int = 128) -> None:
        self._table: dict[tuple[int, str], str] = {}
        self._by_agent: dict[str, set[tuple[int, str]]] = {}
        self._max_t = max(1, max_t)

    def get(self, t: int, node: str) -> str | None:
        """Agent reserved at (t, node) or None."""
        if t < 0 or t > self._max_t:
            return None
        return self._table.get((t, node))

    def is_free(self, t: int, node: str) -> bool:
        return self.get(t, node) is None

    def reserve(self, t: int, node: str, agent_id: str) -> bool:
        """
        Reserve (t, node) for agent_id. Returns False if already taken.
        """
        if t < 0 or t > self._max_t:
            return False
        key = (t, node)
        if key in self._table and self._table[key] != agent_id:
            return False
        self._table[key] = agent_id
        self._by_agent.setdefault(agent_id, set()).add(key)
        return True

    def reserve_path(
        self,
        path: list[tuple[int, str]],
        agent_id: str,
    ) -> bool:
        """
        Reserve full path. Returns False if any (t, node) already taken by another.
        """
        for t, node in path:
            if not self.is_free(t, node) and self.get(t, node) != agent_id:
                return False
        for t, node in path:
            self.reserve(t, node, agent_id)
        return True

    def release_agent(self, agent_id: str) -> None:
        """Remove all reservations for agent_id."""
        keys = self._by_agent.pop(agent_id, set())
        for k in keys:
            self._table.pop(k, None)

    def clear(self) -> None:
        self._table.clear()
        self._by_agent.clear()

    def set_max_t(self, max_t: int) -> None:
        self._max_t = max(1, max_t)
        to_drop = [k for k in self._table if k[0] > self._max_t]
        for k in to_drop:
            aid = self._table.pop(k)
            self._by_agent.get(aid, set()).discard(k)
