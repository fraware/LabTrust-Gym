"""CertifyEdge client resolution for protocol regeneration."""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.pcs.certifyedge_client import resolve_certifyedge_bin


def test_resolve_certifyedge_bin_prefers_sibling_build(repo_root: Path) -> None:
    ce_root = repo_root.parent / "CertifyEdge"
    if not ce_root.is_dir():
        return
    resolved = resolve_certifyedge_bin("certifyedge", ce_root)
    path = Path(resolved)
    assert path.is_file()
    assert "CertifyEdge" in str(path) or path.name.startswith("certifyedge")
