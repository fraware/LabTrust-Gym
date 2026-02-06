"""
Runtime dependency inventory (SBOM-lite) for provenance and supply-chain hardening.

Enumerates installed packages via importlib.metadata, records Python version,
platform, and hash of pyproject.toml. Output is additive metadata only; does not
alter frozen runtime contracts (runner output, receipts, evidence manifest, results v0.2).

Design: no secrets, no absolute filesystem paths in output; stable keys for attestation.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


# Normalized platform string (no paths, no hostnames)
def _platform_identifier() -> str:
    return sys.platform  # e.g. "win32", "linux", "darwin"


def _python_version_string() -> str:
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def _pyproject_toml_hash(repo_root: Path | None) -> str | None:
    """SHA256 hex of pyproject.toml if found; None otherwise. Uses repo_root or package location."""
    if repo_root is not None:
        p = repo_root / "pyproject.toml"
        if p.is_file():
            return hashlib.sha256(p.read_bytes()).hexdigest()
    try:
        from importlib.resources import files

        pkg_root = files("labtrust_gym")
        # When installed, pyproject may not be in package; try parent
        for candidate in (
            pkg_root / ".." / ".." / "pyproject.toml",
            pkg_root / ".." / "pyproject.toml",
        ):
            try:
                path = Path(str(candidate)).resolve()
                if path.is_file():
                    return hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, ValueError):
                continue
    except Exception:
        pass
    return None


def collect_runtime_deps(repo_root: Path | None = None) -> dict[str, Any]:
    """
    Build runtime dependency inventory: installed packages (name, version),
    Python version, platform, and pyproject.toml hash.

    Does not include absolute paths or secrets. Package names and versions only.
    """
    packages: list[dict[str, str]] = []
    try:
        from importlib.metadata import distributions

        for d in distributions():
            meta = d.metadata
            name = getattr(meta, "Name", None) or getattr(meta, "name", None)
            version = getattr(meta, "Version", None) or getattr(meta, "version", None)
            name_str = (name or "").strip() if name is not None else ""
            if not name_str:
                continue
            name_norm = name_str.lower().replace("_", "-")
            packages.append(
                {
                    "name": name_norm,
                    "version": (version or "unknown").strip(),
                }
            )
    except Exception:
        pass
    packages.sort(key=lambda x: (x["name"], x["version"]))

    pyproject_hash = _pyproject_toml_hash(repo_root)

    return {
        "version": "0.1",
        "python_version": _python_version_string(),
        "platform": _platform_identifier(),
        "pyproject_toml_sha256": pyproject_hash,
        "packages": packages,
    }


def write_deps_inventory_runtime(
    out_dir: Path,
    repo_root: Path | None = None,
) -> Path:
    """
    Write SECURITY/deps_inventory_runtime.json under out_dir.

    Returns path to the written file.
    """
    security_dir = out_dir / "SECURITY"
    security_dir.mkdir(parents=True, exist_ok=True)
    out_path = security_dir / "deps_inventory_runtime.json"
    data = collect_runtime_deps(repo_root=repo_root)
    out_path.write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return out_path
