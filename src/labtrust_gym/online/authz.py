"""
Authorization for online API (B007): role hierarchy and path-to-role mapping.

Roles: viewer < runner < admin.
- viewer: public summaries only (GET /v0/summary, GET /health, GET /)
- runner: run tasks, limited summaries (viewer + POST /v0/step)
- admin: run tasks, export artifacts, full logs (runner + GET /v0/export, GET /v0/episode-log, GET /admin/*)
"""

from __future__ import annotations

ROLE_VIEWER = "viewer"
ROLE_RUNNER = "runner"
ROLE_ADMIN = "admin"

# Minimum role level: 0 = viewer, 1 = runner, 2 = admin
_ROLE_LEVEL = {ROLE_VIEWER: 0, ROLE_RUNNER: 1, ROLE_ADMIN: 2}


def role_level(role: str | None) -> int:
    """Return numeric level for role; unknown role = -1."""
    if role is None:
        return -1
    return _ROLE_LEVEL.get(role.strip().lower(), -1)


def has_privilege(user_role: str | None, required_role: str) -> bool:
    """True if user_role has at least the privilege of required_role."""
    return role_level(user_role) >= role_level(required_role)


def required_role_for_path(method: str, path: str) -> str | None:
    """
    Return the minimum role required for this method+path, or None if no auth required for path.

    Paths are normalized (rstrip /). Public: /health, / -> viewer.
    """
    path = path.split("?")[0].rstrip("/") or "/"
    method = method.upper()
    if path in ("/health", "/"):
        return ROLE_VIEWER
    if path == "/v0/summary" and method == "GET":
        return ROLE_VIEWER
    if path in ("/v0/step", "/v0/step/") and method == "POST":
        return ROLE_RUNNER
    if path.startswith("/v0/export") or path.startswith("/admin/"):
        return ROLE_ADMIN
    # B009: raw episode logs only for admin
    if path == "/v0/episode-log" and method == "GET":
        return ROLE_ADMIN
    # Unknown paths: require at least viewer when auth is on
    return ROLE_VIEWER
