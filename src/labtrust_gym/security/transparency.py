"""
Global transparency log for episodes (CT-style): append-only log over episode digests
with Merkle inclusion proofs so anyone can verify a published result was not swapped.

EpisodeDigest.v0.1: sha256 of (results episode block canonicalized, episodes.jsonl hash,
EvidenceBundle manifest hash). Optional and offline; does not change evidence bundle schema.
Adds new artifact TRANSPARENCY_LOG/ only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DIGEST_VERSION = "0.1"
LOG_VERSION = "0.1"


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_string(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _episodes_jsonl_hash(episodes_path: Path) -> str:
    """Canonical line hashing: hash each non-empty line, then hash concatenation of those hashes."""
    raw = episodes_path.read_bytes()
    line_hashes: list[bytes] = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            line_hashes.append(hashlib.sha256(line).digest())
    if not line_hashes:
        return _sha256_hex(b"")
    return _sha256_hex(b"".join(line_hashes))


def _evidence_bundle_manifest_hash(bundle_dir: Path) -> str | None:
    """SHA256 of canonical EvidenceBundle manifest.json (root of bundle). Returns None if no manifest."""
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return _sha256_string(_canonical_json(manifest))


def compute_episode_digest(
    episode_id: str,
    results_episode: dict[str, Any],
    episodes_path: Path,
    bundle_dir: Path | None,
) -> dict[str, Any]:
    """
    Compute EpisodeDigest.v0.1 for one episode.

    Digest = sha256( canonical(results_episode) || episodes.jsonl_hash || bundle_manifest_hash ).
    results_episode: single episode block {seed, metrics} from results.json (v0.2).
    episodes_path: path to episodes.jsonl for this run.
    bundle_dir: EvidenceBundle.v0.1 directory (manifest.json); may be None (use empty hash).
    Returns {episode_id, digest, metadata} with metadata.results_episode_sha256, episodes_jsonl_sha256, evidence_bundle_manifest_sha256.
    """
    results_block_sha = _sha256_string(_canonical_json(results_episode))
    episodes_sha = _episodes_jsonl_hash(episodes_path)
    bundle_sha = _evidence_bundle_manifest_hash(bundle_dir) if bundle_dir else ""
    if not bundle_sha:
        bundle_sha = _sha256_hex(b"")
    payload = results_block_sha + "\n" + episodes_sha + "\n" + bundle_sha
    digest = _sha256_string(payload)
    return {
        "episode_id": episode_id,
        "digest": digest,
        "version": DIGEST_VERSION,
        "metadata": {
            "results_episode_sha256": results_block_sha,
            "episodes_jsonl_sha256": episodes_sha,
            "evidence_bundle_manifest_sha256": bundle_sha if bundle_sha else None,
        },
    }


def build_merkle_tree(digests: list[str]) -> tuple[str, list[dict[str, Any]]]:
    """
    Build Merkle tree from list of digest hex strings.
    Returns (root_hex, proofs) where proofs[i] = {"siblings": [{"hash": h, "position": "left"|"right"}], "leaf_index": i}.
    """
    if not digests:
        root = _sha256_hex(b"")
        return root, []

    def h(x: bytes) -> bytes:
        return hashlib.sha256(x).digest()

    leaves = [bytes.fromhex(d) for d in digests]
    n = len(leaves)
    # Pad to power of 2 (duplicate last leaf)
    size = 1
    while size < n:
        size *= 2
    while len(leaves) < size:
        leaves.append(leaves[-1] if leaves else h(b""))

    # Build tree levels: level[0] = leaves, level[k+1] = parents
    level = list(leaves)
    tree: list[list[bytes]] = [level]
    while len(level) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            next_level.append(h(left + right))
        level = next_level
        tree.append(level)
    root_hex = level[0].hex()

    # Build proof for each original leaf index
    proofs: list[dict[str, Any]] = []
    for idx in range(n):
        siblings: list[dict[str, str]] = []
        pos = idx
        for L in range(len(tree) - 1):
            row = tree[L]
            if pos % 2 == 0:
                other = pos + 1
                side = "right"
            else:
                other = pos - 1
                side = "left"
            if other < len(row):
                siblings.append({"hash": row[other].hex(), "position": side})
            pos //= 2
        proofs.append({"leaf_index": idx, "siblings": siblings})
    return root_hex, proofs


def verify_merkle_proof(leaf_digest: str, proof: dict[str, Any], root: str) -> bool:
    """Verify that leaf_digest is in the tree with given root using proof (siblings + leaf_index)."""
    try:
        current = bytes.fromhex(leaf_digest)
        for s in proof.get("siblings", []):
            sibling = bytes.fromhex(s["hash"])
            pos = s.get("position", "right")
            if pos == "left":
                current = hashlib.sha256(sibling + current).digest()
            else:
                current = hashlib.sha256(current + sibling).digest()
        return current.hex() == root
    except (KeyError, ValueError):
        return False


def discover_episodes(artifact_root: Path) -> list[tuple[str, Path, Path, Path | None]]:
    """
    Discover episodes from paper/release artifact layout: _repr/<task>/{results.json, episodes.jsonl}
    and receipts/<task>/EvidenceBundle.v0.1. Returns list of (episode_id, results_path, episodes_path, bundle_dir).
    """
    out: list[tuple[str, Path, Path, Path | None]] = []
    repr_dir = artifact_root / "_repr"
    receipts_dir = artifact_root / "receipts"
    if not repr_dir.is_dir():
        return out
    for task_dir in sorted(repr_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        task = task_dir.name
        results_path = task_dir / "results.json"
        episodes_path = task_dir / "episodes.jsonl"
        if not results_path.is_file() or not episodes_path.is_file():
            continue
        candidate_bundle = receipts_dir / task / "EvidenceBundle.v0.1"
        bundle_dir: Path | None = candidate_bundle if candidate_bundle.is_dir() else None
        out.append((task, results_path, episodes_path, bundle_dir))
    return out


def _results_episodes_blocks(results_path: Path) -> list[dict[str, Any]]:
    """Load results.json and return list of episode blocks {seed, metrics} (v0.2 schema)."""
    data = json.loads(results_path.read_text(encoding="utf-8"))
    episodes = data.get("episodes") or []
    return [{"seed": e.get("seed"), "metrics": e.get("metrics") or {}} for e in episodes]


def compute_all_digests(artifact_root: Path) -> list[dict[str, Any]]:
    """
    Discover episodes and compute digest for each. For single-episode-per-task we use task as episode_id;
    for multiple episodes we use task_seed or task_index.
    """
    entries: list[dict[str, Any]] = []
    for episode_id, results_path, episodes_path, bundle_dir in discover_episodes(artifact_root):
        blocks = _results_episodes_blocks(results_path)
        if not blocks:
            continue
        for i, block in enumerate(blocks):
            eid = episode_id if len(blocks) == 1 else f"{episode_id}_{block.get('seed', i)}"
            entries.append(compute_episode_digest(eid, block, episodes_path, bundle_dir))
    return entries


def write_transparency_log(
    artifact_root: Path,
    out_dir: Path,
    entries: list[dict[str, Any]] | None = None,
) -> Path:
    """
    Write TRANSPARENCY_LOG/ under out_dir: log.json (append-only list), root.txt, proofs/<episode_id>.json.
    If entries is None, compute from artifact_root via compute_all_digests.
    Returns path to TRANSPARENCY_LOG directory.
    """
    if entries is None:
        entries = compute_all_digests(artifact_root)
    log_dir = out_dir / "TRANSPARENCY_LOG"
    log_dir.mkdir(parents=True, exist_ok=True)
    proofs_dir = log_dir / "proofs"
    proofs_dir.mkdir(parents=True, exist_ok=True)

    digests_ordered = [e["digest"] for e in entries]
    root_hex, proofs = build_merkle_tree(digests_ordered)

    (log_dir / "root.txt").write_text(root_hex + "\n", encoding="utf-8")

    log_artifact: dict[str, Any] = {
        "version": LOG_VERSION,
        "digest_version": DIGEST_VERSION,
        "root": root_hex,
        "entries": entries,
    }
    (log_dir / "log.json").write_text(_canonical_json(log_artifact) + "\n", encoding="utf-8")

    for i, e in enumerate(entries):
        eid = e["episode_id"]
        proof = proofs[i] if i < len(proofs) else {"leaf_index": i, "siblings": []}
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in eid)
        proof_path = proofs_dir / f"{safe_name}.json"
        proof_data = {
            "episode_id": eid,
            "digest": e["digest"],
            "leaf_index": proof["leaf_index"],
            "siblings": proof["siblings"],
            "root": root_hex,
        }
        proof_path.write_text(_canonical_json(proof_data) + "\n", encoding="utf-8")

    return log_dir


LLM_LIVE_TRANSPARENCY_VERSION = "0.1"


def collect_llm_live_metadata_from_pack(pack_out_dir: Path) -> dict[str, Any]:
    """
    Scan pack output baselines/results/*.json for metadata (prompt hashes,
    tool_registry_fingerprint, model_id, latency, cost). Reviewable without
    exposing sensitive prompt text.
    """
    results_dir = pack_out_dir / "baselines" / "results"
    if not results_dir.is_dir():
        return {
            "version": LLM_LIVE_TRANSPARENCY_VERSION,
            "prompt_hashes": [],
            "tool_registry_fingerprint": None,
            "model_version_identifiers": {},
            "latency_and_cost_statistics": {},
            "per_task": {},
        }
    prompt_hashes: list[str] = []
    tool_registry_fingerprint: str | None = None
    model_version_identifiers: dict[str, str] = {}
    latency_cost_agg: dict[str, list[float]] = {
        "mean_latency_ms": [],
        "p95_latency_ms": [],
        "total_tokens": [],
        "estimated_cost_usd": [],
    }
    meta_to_agg = {
        "mean_latency_ms": "mean_latency_ms",
        "mean_llm_latency_ms": "mean_latency_ms",
        "p95_llm_latency_ms": "p95_latency_ms",
        "total_tokens": "total_tokens",
        "estimated_cost_usd": "estimated_cost_usd",
    }
    per_task: dict[str, dict[str, Any]] = {}

    for p in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta = data.get("metadata") or {}
        task_name = data.get("task") or meta.get("task") or (p.stem.split("_")[0] if "_" in p.stem else p.stem)
        pf = meta.get("prompt_fingerprint") or meta.get("prompt_sha256")
        if pf and pf not in prompt_hashes:
            prompt_hashes.append(pf)
        tr = data.get("tool_registry_fingerprint") or meta.get("tool_registry_fingerprint")
        if tr and tool_registry_fingerprint is None:
            tool_registry_fingerprint = tr
        bid = meta.get("llm_backend_id") or data.get("llm_backend_id")
        mid = meta.get("llm_model_id") or data.get("llm_model_id")
        if bid:
            model_version_identifiers["llm_backend_id"] = str(bid)
        if mid:
            model_version_identifiers["llm_model_id"] = str(mid)
        for meta_key, agg_key in meta_to_agg.items():
            v = meta.get(meta_key)
            if v is not None and agg_key in latency_cost_agg:
                try:
                    latency_cost_agg[agg_key].append(float(v))
                except (TypeError, ValueError):
                    pass
        per_task[task_name] = {
            "prompt_fingerprint": pf,
            "llm_model_id": mid,
            "llm_backend_id": bid,
            "mean_latency_ms": meta.get("mean_latency_ms"),
            "p95_llm_latency_ms": meta.get("p95_llm_latency_ms"),
            "total_tokens": meta.get("total_tokens"),
            "estimated_cost_usd": meta.get("estimated_cost_usd"),
        }

    def _agg(lst: list[float]) -> dict[str, float]:
        if not lst:
            return {}
        return {
            "min": min(lst),
            "max": max(lst),
            "mean": sum(lst) / len(lst),
            "sum": sum(lst),
        }

    latency_and_cost_statistics: dict[str, Any] = {}
    if latency_cost_agg["mean_latency_ms"]:
        latency_and_cost_statistics["mean_latency_ms"] = _agg(latency_cost_agg["mean_latency_ms"])
    if latency_cost_agg["p95_latency_ms"]:
        latency_and_cost_statistics["p95_latency_ms"] = _agg(latency_cost_agg["p95_latency_ms"])
    if latency_cost_agg["total_tokens"]:
        latency_and_cost_statistics["total_tokens"] = _agg(latency_cost_agg["total_tokens"])
    if latency_cost_agg["estimated_cost_usd"]:
        latency_and_cost_statistics["estimated_cost_usd"] = _agg(
            latency_cost_agg["estimated_cost_usd"]
        )

    return {
        "version": LLM_LIVE_TRANSPARENCY_VERSION,
        "prompt_hashes": sorted(prompt_hashes),
        "tool_registry_fingerprint": tool_registry_fingerprint,
        "model_version_identifiers": model_version_identifiers,
        "latency_and_cost_statistics": latency_and_cost_statistics,
        "per_task": per_task,
    }


def write_llm_live_transparency_log(pack_out_dir: Path) -> Path:
    """
    Write TRANSPARENCY_LOG/llm_live.json from pack output. Records prompt hashes,
    tool registry fingerprint, model version identifiers, latency and cost
    statistics. No sensitive prompt text. Call when pipeline_mode is llm_live.
    """
    log_dir = pack_out_dir / "TRANSPARENCY_LOG"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = collect_llm_live_metadata_from_pack(pack_out_dir)
    out_path = log_dir / "llm_live.json"
    out_path.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
    return log_dir
