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
from typing import Any

# Token in docs/coordination_benchmark_card.md replaced with fingerprint block at render time
COORDINATION_POLICY_FINGERPRINT_TOKEN = "COORDINATION_POLICY_FINGERPRINT_TOKEN"

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
) -> list[tuple[str, str]]:
    """
    Return sorted list of (relative_path, sha256_hex) for each coordination policy file.
    relative_path is under policy/coordination (e.g. coordination_study_spec.v0.1.yaml).
    """
    root = Path(repo_root).resolve()
    coord_dir = root / Path(*policy_subdir.split("/"))
    if not coord_dir.is_dir():
        return []
    out: list[tuple[str, str]] = []
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
    replacing the policy fingerprint token with the actual fingerprint
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
    if COORDINATION_POLICY_FINGERPRINT_TOKEN in body:
        body = body.replace(COORDINATION_POLICY_FINGERPRINT_TOKEN, replacement)
    else:
        body = body.rstrip() + "\n\n" + replacement + "\n"

    return body


def _default_coordination_card_content() -> str:
    """Fallback card content when template is missing. Includes all sections required for scientific review."""
    return (
        """# Coordination Benchmark Card (coord_scale / coord_risk)

## Scope

coord_scale and coord_risk evaluate multi-agent coordination in the Blood Sciences lane.

## Scenario generation

Scenarios are defined in the coordination study spec and scale configs; see policy/coordination.

## Scale configs

Scale configs (policy/coordination/scale_configs.v0.1.yaml) define agent counts, devices, and episode length.

## Methods

Coordination methods are registered in policy/coordination/coordination_methods.v0.1.yaml.

## Injections

Injections (policy/coordination/injections.v0.2.yaml) define adversarial and fault-injection scenarios for the pack.

## Metrics definitions

Metrics (violations, detection latency, attack success) are defined in the study spec and gate policy.

## Determinism guarantees

Runs with the same seed and policy produce deterministic episode outcomes; fingerprint documents policy version.

## What this benchmark is NOT measuring

This card does not certify safety of deployed systems; it documents benchmark scope and policy for reproducibility.

## Policy fingerprint

"""
        + COORDINATION_POLICY_FINGERPRINT_TOKEN
        + """
"""
    )


def write_coordination_card(
    out_path: Path,
    repo_root: Path,
    include_file_hashes: bool = True,
) -> None:
    """Write rendered COORDINATION_CARD.md to out_path."""
    content = render_coordination_card(repo_root, include_file_hashes=include_file_hashes)
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")


# Fallback LLM method_ids when registry cannot be loaded (coordination_class: llm / llm_based: true)
LLM_COORDINATION_METHOD_IDS_FALLBACK = [
    "llm_constrained",
    "llm_central_planner",
    "llm_hierarchical_allocator",
    "llm_auction_bidder",
    "llm_gossip_summarizer",
]

# Backends for LLM coordination (CLI --llm-backend)
LLM_BACKEND_IDS = ["deterministic", "openai_live", "ollama_live"]


def _get_llm_coordination_method_ids(coord_dir: Path) -> list[str]:
    """LLM method_ids from registry (llm_based or coordination_class llm); else fallback list."""
    reg_path = coord_dir / "coordination_methods.v0.1.yaml"
    if not reg_path.is_file():
        return list(LLM_COORDINATION_METHOD_IDS_FALLBACK)
    try:
        from labtrust_gym.policy.coordination import list_llm_coordination_method_ids

        return list_llm_coordination_method_ids(reg_path)
    except Exception:
        return list(LLM_COORDINATION_METHOD_IDS_FALLBACK)


def _load_yaml_safe(path: Path) -> dict[str, Any]:
    """Load YAML file; return empty dict if missing or invalid."""
    if not path.is_file():
        return {}
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def render_coordination_llm_card(
    repo_root: Path,
    policy_subdir: str = "policy/coordination",
) -> str:
    """
    Render COORDINATION_LLM_CARD.md: LLM methods, backends, policy fingerprint,
    injection coverage for LLM-relevant risks, and known limitations.
    """
    root = Path(repo_root).resolve()
    coord_dir = root / Path(*policy_subdir.split("/"))
    fingerprint = coordination_policy_fingerprint(root, policy_subdir)

    methods_reg = _load_yaml_safe(coord_dir / "coordination_methods.v0.1.yaml")
    injections_cfg = _load_yaml_safe(coord_dir / "injections.v0.2.yaml")
    matrix_cfg = _load_yaml_safe(coord_dir / "method_risk_matrix.v0.1.yaml")

    llm_method_ids = _get_llm_coordination_method_ids(coord_dir)
    method_rows: list[dict[str, Any]] = []
    for m in (methods_reg.get("coordination_methods") or {}).get("methods") or []:
        if m.get("method_id") in llm_method_ids:
            method_rows.append(m)

    injection_ids: list[str] = []
    for inj in injections_cfg.get("injections") or []:
        iid = inj.get("injection_id")
        if iid:
            injection_ids.append(str(iid))

    llm_risk_cells: list[dict[str, Any]] = []
    for c in (matrix_cfg.get("method_risk_matrix") or {}).get("cells") or []:
        if c.get("method_id") in llm_method_ids:
            llm_risk_cells.append(c)

    lines = [
        "# Coordination LLM Card (LLM-based methods)",
        "",
        "This card lists LLM-based coordination methods, supported backends, policy fingerprint, injection coverage for security evaluation, and known limitations. For the full coordination protocol see docs/llm_coordination_protocol.md in the repository.",
        "",
        "## LLM coordination methods",
        "",
        "| method_id | name | known_weaknesses | required_controls |",
        "|-----------|------|------------------|-------------------|",
    ]
    for m in method_rows:
        mid = m.get("method_id", "")
        name = (m.get("name") or "").replace("|", "\\|")
        weaknesses = ", ".join(m.get("known_weaknesses") or [])
        controls = ", ".join(m.get("required_controls") or [])
        lines.append(f"| {mid} | {name} | {weaknesses} | {controls} |")

    lines.extend(
        [
            "",
            "## Backends",
            "",
            "| backend_id | description |",
            "|------------|-------------|",
            "| deterministic | Seeded proposal backend; no network; reproducible. |",
            "| openai_live | Live OpenAI (CoordinationProposal or market bids); used by llm_central_planner, llm_hierarchical_allocator, llm_auction_bidder; requires OPENAI_API_KEY. |",
            "| ollama_live | Live Ollama (CoordinationProposal or market bids); same methods as openai_live when configured (LABTRUST_LOCAL_LLM_URL, LABTRUST_LOCAL_LLM_MODEL). |",
            "",
            "Default for `run-coordination-study` and `run-benchmark` when using LLM methods: **deterministic**. No API calls unless `--llm-backend openai_live` (or ollama_live) is passed.",
            "",
            "## Policy fingerprint",
            "",
            f"Same as coordination policy: **SHA-256** `{fingerprint}` (see COORDINATION_CARD.md for per-file hashes).",
            "",
            "## Injection coverage (security evaluation)",
            "",
            "coord_risk injections used for security evaluation (from injections.v0.2.yaml):",
            "",
        ]
    )
    for iid in sorted(injection_ids):
        lines.append(f"- {iid}")
    lines.extend(
        [
            "",
            "LLM-relevant injections include: INJ-LLM-PROMPT-INJECT-COORD-001, INJ-LLM-TOOL-ESCALATION-001, INJ-COMMS-FLOOD-LLM-001, INJ-ID-REPLAY-COORD-001, INJ-COLLUSION-MARKET-001, INJ-MEMORY-POISON-COORD-001, INJ-ID-SPOOF-001, INJ-COMMS-POISON-001, INJ-BID-SPOOF-001, INJ-COLLUSION-001, and others as defined in the spec.",
            "",
            "Method-risk matrix (required_bench / coverage) for LLM methods is in policy/coordination/method_risk_matrix.v0.1.yaml. Run with `--llm-backend deterministic` to satisfy coverage gates without network.",
            "",
            "## Known limitations",
            "",
            "- **Deterministic backend**: Proposals are seeded NOOP or trivial; not representative of live LLM quality. Use for reproducibility and coverage only.",
            "- **Live backends**: Require API key (openai_live) or local service (ollama_live); cost and latency vary; results non-deterministic.",
            "- **Shield and repair**: LLM proposals are passed through RBAC/signature shield; blocked actions trigger repair loop. Repair caps (max_repairs, blocked_threshold) are configurable via scale_config. Security metrics (attack_success_rate, detection, containment) depend on injection and harness.",
            "- **Injection set**: Only configured injections in the study spec are applied; no black-box adversary search.",
            "",
        ]
    )
    return "\n".join(lines)


def write_coordination_llm_card(
    out_path: Path,
    repo_root: Path,
) -> None:
    """Write COORDINATION_LLM_CARD.md to out_path (e.g. package-release output)."""
    content = render_coordination_llm_card(Path(repo_root))
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

    manifest_files: list[dict[str, str]] = []
    for name, h in hashes:
        src = coord_dir / name
        if src.is_file():
            shutil.copy2(src, dest / name)
            manifest_files.append({"path": name, "sha256": h})

    manifest: dict[str, Any] = {
        "coordination_policy_fingerprint": fingerprint,
        "policy_subdir": policy_subdir,
        "files": manifest_files,
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return fingerprint
