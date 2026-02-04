"""
Render the coordination benchmark card (COORDINATION_CARD.md) from the docs template
and policy registries, and compute a stable fingerprint of the coordination policy set.

Used by package-release (paper_v0.1) to produce a scientifically reviewable coordination
card with deterministic policy fingerprint and optional frozen policy copy.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Relative to repo_root / "policy" / "coordination"
COORDINATION_POLICY_FILES = [
    "coordination_study_spec.v0.1.yaml",
    "scale_configs.v0.1.yaml",
    "coordination_methods.v0.1.yaml",
    "method_risk_matrix.v0.1.yaml",
    "resilience_scoring.v0.1.yaml",
]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_hashes(
    repo_root: Path,
    policy_subdir: str = "policy/coordination",
) -> List[Tuple[str, str]]:
    """
    Return sorted list of (relative_path, sha256_hex) for each coordination policy file.
    relative_path is under policy/coordination (e.g. coordination_study_spec.v0.1.yaml).
    """
    root = Path(repo_root).resolve()
    coord_dir = root / Path(*policy_subdir.split("/"))
    if not coord_dir.is_dir():
        return []
    out: List[Tuple[str, str]] = []
    for name in sorted(COORDINATION_POLICY_FILES):
        path = coord_dir / name
        if path.is_file():
            out.append((name, _sha256_bytes(path.read_bytes())))
    return out


def coordination_policy_fingerprint(
    repo_root: Path,
    policy_subdir: str = "policy/coordination",
) -> str:
    """
    Compute a stable fingerprint of the coordination policy set.
    Fingerprint = SHA-256 (hex) of the concatenation of sorted (path, file_sha256) strings.
    Same files => same fingerprint; any change in content or set => different fingerprint.
    """
    hashes = _file_hashes(repo_root, policy_subdir)
    if not hashes:
        return hashlib.sha256(b"no-coordination-policy-files").hexdigest()
    payload = "".join(f"{path}\0{h}" for path, h in hashes).encode("utf-8")
    return _sha256_bytes(payload)


def render_coordination_card(
    repo_root: Path,
    include_file_hashes: bool = True,
    policy_subdir: str = "policy/coordination",
) -> str:
    """
    Render COORDINATION_CARD.md from docs/coordination_benchmark_card.md,
    replacing the policy fingerprint placeholder with the actual fingerprint
    and optional per-file hashes table.
    """
    root = Path(repo_root).resolve()
    template_path = root / "docs" / "coordination_benchmark_card.md"
    if template_path.exists():
        body = template_path.read_text(encoding="utf-8")
    else:
        body = _default_coordination_card_content()

    fingerprint = coordination_policy_fingerprint(root, policy_subdir)
    hashes = _file_hashes(root, policy_subdir)

    block_lines = [
        f"**Fingerprint (SHA-256):** `{fingerprint}`",
        "",
    ]
    if include_file_hashes and hashes:
        block_lines.append("| File | SHA-256 |")
        block_lines.append("|------|---------|")
        for path, h in hashes:
            block_lines.append(f"| `{path}` | `{h}` |")
        block_lines.append("")

    replacement = "\n".join(block_lines)
    if "COORDINATION_POLICY_FINGERPRINT_PLACEHOLDER" in body:
        body = body.replace("COORDINATION_POLICY_FINGERPRINT_PLACEHOLDER", replacement)
    else:
        body = body.rstrip() + "\n\n" + replacement + "\n"

    return body


def _default_coordination_card_content() -> str:
    """Fallback card content when template is missing."""
    return """# Coordination Benchmark Card (TaskG / TaskH)

## Scope

TaskG_COORD_SCALE and TaskH_COORD_RISK evaluate multi-agent coordination in the Blood Sciences lane.

## Policy fingerprint

COORDINATION_POLICY_FINGERPRINT_PLACEHOLDER
"""


def write_coordination_card(
    out_path: Path,
    repo_root: Path,
    include_file_hashes: bool = True,
) -> None:
    """Write rendered COORDINATION_CARD.md to out_path."""
    content = render_coordination_card(
        repo_root, include_file_hashes=include_file_hashes
    )
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")


def copy_frozen_coordination_policy(
    repo_root: Path,
    dest_dir: Path,
    policy_subdir: str = "policy/coordination",
) -> str:
    """
    Copy coordination policy files to dest_dir and write manifest.json with
    fingerprint and per-file sha256. Returns the coordination policy fingerprint.
    """
    root = Path(repo_root).resolve()
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    coord_dir = root / Path(*policy_subdir.split("/"))
    hashes = _file_hashes(root, policy_subdir)
    fingerprint = coordination_policy_fingerprint(root, policy_subdir)

    manifest_files: List[Dict[str, str]] = []
    for name, h in hashes:
        src = coord_dir / name
        if src.is_file():
            shutil.copy2(src, dest / name)
            manifest_files.append({"path": name, "sha256": h})

    manifest: Dict[str, Any] = {
        "coordination_policy_fingerprint": fingerprint,
        "policy_subdir": policy_subdir,
        "files": manifest_files,
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return fingerprint
