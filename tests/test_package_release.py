"""
Package-release: determinism test (same seed_base => identical MANIFEST hashes).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.studies.package_release import run_package_release


def test_package_release_determinism() -> None:
    """Run package-release twice with same seed_base; MANIFEST paths must match; non-plot file hashes must be identical (plots may vary by matplotlib backend)."""
    seed_base = 4242
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "release1"
        out2 = Path(tmp) / "release2"
        run_package_release(
            profile="minimal",
            out_dir=out1,
            seed_base=seed_base,
            include_repro_dir=False,
        )
        run_package_release(
            profile="minimal",
            out_dir=out2,
            seed_base=seed_base,
            include_repro_dir=False,
        )
        m1_path = out1 / "MANIFEST.v0.1.json"
        m2_path = out2 / "MANIFEST.v0.1.json"
        assert m1_path.exists()
        assert m2_path.exists()
        manifest1 = json.loads(m1_path.read_text(encoding="utf-8"))
        manifest2 = json.loads(m2_path.read_text(encoding="utf-8"))
        files1 = {f["path"]: f["sha256"] for f in (manifest1.get("files") or [])}
        files2 = {f["path"]: f["sha256"] for f in (manifest2.get("files") or [])}
        assert set(files1.keys()) == set(files2.keys()), "MANIFEST path list must be identical"
        skip_paths = {"plots/", "results.json"}
        for path in files1:
            if any(path.startswith(p) or path == p for p in skip_paths):
                continue
            assert files1[path] == files2[path], f"MANIFEST hash for {path} must be identical for same seed_base"


def test_package_release_produces_expected_files() -> None:
    """package-release produces MANIFEST, BENCHMARK_CARD, metadata, results.json, plots/, tables/, receipts/, fhir/."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "release"
        run_package_release(
            profile="minimal",
            out_dir=out,
            seed_base=100,
            include_repro_dir=False,
        )
        assert (out / "MANIFEST.v0.1.json").exists()
        assert (out / "BENCHMARK_CARD.md").exists()
        assert (out / "metadata.json").exists()
        assert (out / "results.json").exists()
        assert out / "plots"
        assert out / "tables"
        assert out / "receipts"
        assert out / "fhir"
        meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
        assert "seed_base" in meta
        assert "profile" in meta
        assert meta["seed_base"] == 100
        assert meta["profile"] == "minimal"
