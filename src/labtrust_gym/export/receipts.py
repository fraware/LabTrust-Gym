"""
Receipt and Evidence Bundle export from episode log (JSONL).

- Receipt.v0.1: per specimen/result with identifiers, timestamps, decision,
  reason_codes, tokens, critical comm, invariant/enforcement summary, hashchain.
- EvidenceBundle.v0.1: directory with receipt(s), episode_log_subset, manifest,
  invariant_eval_trace, enforcement_actions, hashchain_proof.
Deterministic: same input log => identical outputs (canonical JSON, stable filenames).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.tools.registry import combined_policy_fingerprint

RECEIPT_VERSION = "0.1"
MANIFEST_VERSION = "0.1"
EVIDENCE_BUNDLE_DIR = "EvidenceBundle.v0.1"


def load_episode_log(path: Path) -> list[dict[str, Any]]:
    """Load episode log JSONL; one dict per line. Deterministic order."""
    entries: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    return entries


def _canonical_json(obj: Any) -> str:
    """Canonical JSON (sort_keys) for deterministic hashes."""
    return json.dumps(obj, sort_keys=True)


def _entity_ids_from_entries(
    entries: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """Collect specimen_id and result_id from log entries (args). Deterministic sorted."""
    specimen_ids: set[str] = set()
    result_ids: set[str] = set()
    for e in entries:
        args = e.get("args") or {}
        if isinstance(args, dict):
            sid = args.get("specimen_id")
            if sid:
                specimen_ids.add(str(sid))
            rid = args.get("result_id")
            if rid:
                result_ids.add(str(rid))
        action = e.get("action_type", "")
        if action == "CREATE_ACCESSION" and args.get("specimen_id"):
            specimen_ids.add(str(args["specimen_id"]))
        if action in (
            "GENERATE_RESULT",
            "RELEASE_RESULT",
            "HOLD_RESULT",
            "NOTIFY_CRITICAL_RESULT",
            "ACK_CRITICAL_RESULT",
        ) and args.get("result_id"):
            result_ids.add(str(args["result_id"]))
    return sorted(specimen_ids), sorted(result_ids)


def _decision_for_entity(
    entity_type: str,
    entity_id: str,
    entries: list[dict[str, Any]],
) -> str:
    """Infer decision: RELEASED, HELD, REJECTED, or BLOCKED from last relevant step."""
    last_status: str | None = None
    last_action: str | None = None
    for e in entries:
        args = e.get("args") or {}
        if not isinstance(args, dict):
            continue
        if entity_type == "specimen" and args.get("specimen_id") != entity_id:
            continue
        if entity_type == "result" and args.get("result_id") != entity_id:
            continue
        action = e.get("action_type", "")
        if entity_type == "specimen":
            if action in (
                "REJECT_SPECIMEN",
                "ACCEPT_SPECIMEN",
                "HOLD_SPECIMEN",
                "CREATE_ACCESSION",
            ):
                last_action = action
                last_status = e.get("status")
        else:
            if action in ("RELEASE_RESULT", "HOLD_RESULT", "GENERATE_RESULT"):
                last_action = action
                last_status = e.get("status")
    if last_status == "BLOCKED":
        return "BLOCKED"
    if last_action == "RELEASE_RESULT":
        return "RELEASED"
    if last_action == "HOLD_RESULT" or last_action == "HOLD_SPECIMEN":
        return "HELD"
    if last_action == "REJECT_SPECIMEN":
        return "REJECTED"
    if entity_type == "specimen" and last_action == "ACCEPT_SPECIMEN":
        return "RELEASED"
    if entity_type == "result":
        return "RELEASED" if last_action == "GENERATE_RESULT" else "BLOCKED"
    return "BLOCKED"


def _timestamps_for_entity(
    entity_type: str,
    entity_id: str,
    entries: list[dict[str, Any]],
) -> dict[str, int]:
    """Collect timestamps (t_s) for received, accepted, separated, queued, run_started, result_generated, released."""
    out: dict[str, int] = {}
    for e in entries:
        args = e.get("args") or {}
        if not isinstance(args, dict):
            continue
        if entity_type == "specimen" and args.get("specimen_id") != entity_id:
            continue
        if entity_type == "result" and args.get("result_id") != entity_id:
            continue
        t_s = int(e.get("t_s", 0))
        action = e.get("action_type", "")
        if action == "CREATE_ACCESSION":
            out["received"] = t_s
        if action == "ACCEPT_SPECIMEN":
            out["accepted"] = t_s
        if action == "GENERATE_RESULT":
            out["result_generated"] = t_s
        if action == "RELEASE_RESULT":
            out["released"] = t_s
        if "QUEUE" in action or action == "START_RUN":
            if "queued" not in out:
                out["queued"] = t_s
        if action == "START_RUN":
            out["run_started"] = t_s
    return out


def _reason_codes_for_entity(
    entity_type: str,
    entity_id: str,
    entries: list[dict[str, Any]],
) -> list[str]:
    """Collect reason_codes from blocked_reason_code and violations."""
    codes: list[str] = []
    seen: set[str] = set()
    for e in entries:
        args = e.get("args") or {}
        if not isinstance(args, dict):
            continue
        if entity_type == "specimen" and args.get("specimen_id") != entity_id:
            continue
        if entity_type == "result" and args.get("result_id") != entity_id:
            continue
        rc = e.get("blocked_reason_code")
        if rc and rc not in seen:
            codes.append(rc)
            seen.add(rc)
        for v in e.get("violations") or []:
            rcv = v.get("reason_code")
            if rcv and rcv not in seen:
                codes.append(rcv)
                seen.add(rcv)
    return codes


def _tokens_for_entity(
    entity_type: str,
    entity_id: str,
    entries: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Tokens consumed linked to step index; minted/revoked from emits if present."""
    consumed: list[dict[str, Any]] = []
    for i, e in enumerate(entries):
        args = e.get("args") or {}
        if not isinstance(args, dict):
            continue
        if entity_type == "specimen" and args.get("specimen_id") != entity_id:
            continue
        if entity_type == "result" and args.get("result_id") != entity_id:
            continue
        for tid in e.get("token_consumed") or []:
            consumed.append({"token_id": tid, "step_index": i})
    return {"minted": [], "consumed": consumed, "revoked": []}


def _invariant_summary_for_entity(
    entity_type: str,
    entity_id: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Violated invariant_ids, first_violation_ts, final_status."""
    violated: list[str] = []
    first_ts: int | None = None
    for e in entries:
        args = e.get("args") or {}
        if not isinstance(args, dict):
            continue
        if entity_type == "specimen" and args.get("specimen_id") != entity_id:
            continue
        if entity_type == "result" and args.get("result_id") != entity_id:
            continue
        for v in e.get("violations") or []:
            if v.get("status") == "VIOLATION":
                inv_id = v.get("invariant_id")
                if inv_id and inv_id not in violated:
                    violated.append(inv_id)
                if first_ts is None:
                    first_ts = int(e.get("t_s", 0))
        if violated and first_ts is None:
            first_ts = int(e.get("t_s", 0))
    return {
        "violated_ids": violated,
        "first_violation_ts": first_ts,
        "final_status": "VIOLATION" if violated else "PASS",
    }


def _enforcement_summary_for_entity(
    entity_type: str,
    entity_id: str,
    entries: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Throttle, kill_switch, freeze_zone, forensic_freeze from enforcements in relevant steps."""
    throttle: list[dict[str, Any]] = []
    kill_switch: list[dict[str, Any]] = []
    freeze_zone: list[dict[str, Any]] = []
    forensic_freeze: list[dict[str, Any]] = []
    for e in entries:
        args = e.get("args") or {}
        if not isinstance(args, dict):
            continue
        if entity_type == "specimen" and args.get("specimen_id") != entity_id:
            continue
        if entity_type == "result" and args.get("result_id") != entity_id:
            continue
        for enf in e.get("enforcements") or []:
            t = enf.get("type")
            rec = {**enf, "t_s": e.get("t_s")}
            if t == "throttle_agent":
                throttle.append(rec)
            elif t == "kill_switch":
                kill_switch.append(rec)
            elif t == "freeze_zone":
                freeze_zone.append(rec)
            elif t == "forensic_freeze":
                forensic_freeze.append(rec)
    return {
        "throttle": throttle,
        "kill_switch": kill_switch,
        "freeze_zone": freeze_zone,
        "forensic_freeze": forensic_freeze,
    }


def _signature_summary_from_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Signature verification summary: total_verified, total_failed, first_failure_reason_code, failing_reason_codes."""
    total_verified = 0
    total_failed = 0
    first_failure_reason_code: str | None = None
    failing_reason_codes: list[str] = []
    seen_codes: set[str] = set()
    for e in entries:
        sv = e.get("signature_verification")
        if not isinstance(sv, dict):
            continue
        passed = sv.get("passed")
        if passed is True:
            total_verified += 1
        elif passed is False:
            total_failed += 1
            rc = sv.get("reason_code")
            if rc and rc not in seen_codes:
                seen_codes.add(rc)
                failing_reason_codes.append(rc)
                if first_failure_reason_code is None:
                    first_failure_reason_code = rc
    return {
        "total_verified": total_verified,
        "total_failed": total_failed,
        "first_failure_reason_code": first_failure_reason_code,
        "failing_reason_codes": failing_reason_codes,
    }


def _hashchain_from_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Last hashchain state from entries (last line with hashchain)."""
    for e in reversed(entries):
        h = e.get("hashchain")
        if h and isinstance(h, dict):
            return {
                "head_hash": h.get("head_hash", ""),
                "last_event_hash": h.get("last_event_hash", ""),
                "length": int(h.get("length", 0)),
                "break_status": (
                    "broken"
                    if e.get("emits")
                    and ("FORENSIC_FREEZE" in str(e.get("emits")) or "FORENSIC_FREEZE_LOG" in str(e.get("emits")))
                    else "intact"
                ),
            }
    return {
        "head_hash": "",
        "last_event_hash": "",
        "length": 0,
        "break_status": "intact",
    }


def _chain_of_custody_for_specimen(
    entity_id: str,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Chain-of-custody transport events for this specimen (forensic quality). DISPATCH -> CHAIN_OF_CUSTODY_SIGN -> RECEIVE."""
    consignment_to_specimens: dict[str, list[str]] = {}
    for e in entries:
        if e.get("action_type") != "DISPATCH_TRANSPORT":
            continue
        cid = e.get("consignment_id")
        args = e.get("args") or {}
        specimen_ids = list(args.get("specimen_ids") or [])
        if cid and entity_id in specimen_ids:
            consignment_to_specimens[cid] = specimen_ids
    if not consignment_to_specimens:
        return []
    out: list[dict[str, Any]] = []
    for e in entries:
        action = e.get("action_type", "")
        t_s = int(e.get("t_s", 0))
        args = e.get("args") or {}
        cid = args.get("consignment_id") or e.get("consignment_id")
        if action == "DISPATCH_TRANSPORT" and cid and cid in consignment_to_specimens:
            out.append(
                {
                    "action_type": "DISPATCH_TRANSPORT",
                    "t_s": t_s,
                    "consignment_id": cid,
                    "status": e.get("status"),
                }
            )
        elif action == "CHAIN_OF_CUSTODY_SIGN" and cid and cid in consignment_to_specimens:
            out.append(
                {
                    "action_type": "CHAIN_OF_CUSTODY_SIGN",
                    "t_s": t_s,
                    "consignment_id": cid,
                    "status": e.get("status"),
                    "agent_id": e.get("agent_id"),
                }
            )
        elif action == "RECEIVE_TRANSPORT" and cid and cid in consignment_to_specimens:
            out.append(
                {
                    "action_type": "RECEIVE_TRANSPORT",
                    "t_s": t_s,
                    "consignment_id": cid,
                    "status": e.get("status"),
                }
            )
    return out


def build_receipt(
    entity_type: str,
    entity_id: str,
    entries: list[dict[str, Any]],
    hashchain_fallback: dict[str, Any],
) -> dict[str, Any]:
    """Build one Receipt.v0.1 dict for a specimen or result."""
    decision = _decision_for_entity(entity_type, entity_id, entries)
    timestamps = _timestamps_for_entity(entity_type, entity_id, entries)
    reason_codes = _reason_codes_for_entity(entity_type, entity_id, entries)
    tokens = _tokens_for_entity(entity_type, entity_id, entries)
    invariant_summary = _invariant_summary_for_entity(entity_type, entity_id, entries)
    enforcement_summary = _enforcement_summary_for_entity(entity_type, entity_id, entries)
    hc = hashchain_fallback
    for e in reversed(entries):
        args = e.get("args") or {}
        if not isinstance(args, dict):
            continue
        if entity_type == "specimen" and args.get("specimen_id") == entity_id:
            hc = e.get("hashchain") or hc
            break
        if entity_type == "result" and args.get("result_id") == entity_id:
            hc = e.get("hashchain") or hc
            break
    if isinstance(hc, dict):
        hc = {
            "head_hash": hc.get("head_hash", ""),
            "last_event_hash": hc.get("last_event_hash", ""),
            "length": int(hc.get("length", 0)),
            "break_status": "intact",
        }
    else:
        hc = hashchain_fallback

    signature_summary = _signature_summary_from_entries(entries)
    receipt: dict[str, Any] = {
        "version": RECEIPT_VERSION,
        "entity_type": entity_type,
        "decision": decision,
        "timestamps": timestamps,
        "reason_codes": reason_codes,
        "tokens": tokens,
        "critical_comm_records": {"attempts": [], "ack_summary": []},
        "invariant_summary": invariant_summary,
        "enforcement_summary": enforcement_summary,
        "signature_summary": signature_summary,
        "hashchain": hc,
    }
    if entity_type == "specimen":
        receipt["specimen_id"] = entity_id
        receipt["result_id"] = None
        chain_of_custody = _chain_of_custody_for_specimen(entity_id, entries)
        if chain_of_custody:
            receipt["chain_of_custody"] = chain_of_custody
    else:
        receipt["specimen_id"] = None
        receipt["result_id"] = entity_id
    receipt["accession_ids"] = []
    receipt["panel_id"] = None
    receipt["device_ids"] = []
    if entity_type == "result":
        for e in entries:
            args = e.get("args") or {}
            if args.get("result_id") != entity_id:
                continue
            if e.get("action_type") == "GENERATE_RESULT":
                if args.get("panel_id"):
                    receipt["panel_id"] = args.get("panel_id")
                if args.get("device_id"):
                    receipt["device_ids"] = [args["device_id"]]
                break
    # LLM audit: from last entry that touches this entity and has audit hashes
    llm_audit = None
    for e in reversed(entries):
        args = e.get("args") or {}
        if not isinstance(args, dict):
            continue
        if entity_type == "specimen" and args.get("specimen_id") != entity_id:
            continue
        if entity_type == "result" and args.get("result_id") != entity_id:
            continue
        if e.get("prompt_hash") is not None:
            llm_audit = {
                "prompt_hash": e.get("prompt_hash"),
                "policy_summary_hash": e.get("policy_summary_hash"),
                "allowed_actions_hash": e.get("allowed_actions_hash"),
                "decoder_version": e.get("decoder_version"),
            }
            break
    if llm_audit:
        receipt["llm_audit"] = llm_audit
    return receipt


def build_receipts_from_log(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build Receipt.v0.1 list for all specimens and results in the log. Deterministic order."""
    specimen_ids, result_ids = _entity_ids_from_entries(entries)
    hc_fallback = _hashchain_from_entries(entries)
    receipts: list[dict[str, Any]] = []
    for sid in specimen_ids:
        receipts.append(build_receipt("specimen", sid, entries, hc_fallback))
    for rid in result_ids:
        receipts.append(build_receipt("result", rid, entries, hc_fallback))
    return receipts


def _sha256_file(path: Path) -> str:
    """SHA-256 hex digest of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_string(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


POLICY_PACK_MANIFEST_FILENAME = "policy_pack_manifest.v0.1.json"


def write_evidence_bundle(
    out_dir: Path,
    receipts: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    policy_fingerprint: str | None = None,
    partner_id: str | None = None,
    sign_bundle: bool = False,
    policy_root: Path | None = None,
    tool_registry_fingerprint: str | None = None,
    rbac_policy_fingerprint: str | None = None,
) -> Path:
    """
    Write EvidenceBundle.v0.1/ under out_dir.
    Contents: receipt(s), episode_log_subset.jsonl, invariant_eval_trace.jsonl,
    enforcement_actions.jsonl, hashchain_proof.json, optional policy_pack_manifest.v0.1.json, manifest.
    When policy_root and partner_id are set, writes policy_pack_manifest and sets policy_root_hash
    on manifest and each receipt.
    Returns path to bundle directory.
    """
    bundle_dir = out_dir / EVIDENCE_BUNDLE_DIR
    bundle_dir.mkdir(parents=True, exist_ok=True)

    policy_root_hash: str | None = None
    if policy_root is not None and partner_id is not None:
        try:
            from labtrust_gym.policy.loader import build_policy_pack_manifest

            policy_manifest = build_policy_pack_manifest(Path(policy_root), partner_id=partner_id)
            policy_root_hash = policy_manifest.get("root_hash")
            policy_manifest_path = bundle_dir / POLICY_PACK_MANIFEST_FILENAME
            policy_manifest_path.write_text(_canonical_json(policy_manifest) + "\n", encoding="utf-8")
        except Exception:
            policy_root_hash = None

    # Deterministic filenames: receipt_<type>_<id>.v0.1.json; id sanitized for filename
    def _safe_filename(s: str) -> str:
        return "".join(c if c.isalnum() or c in "_-" else "_" for c in s)

    written_files: list[str] = []
    if policy_root_hash is not None:
        written_files.append(POLICY_PACK_MANIFEST_FILENAME)
    for r in receipts:
        rec = dict(r)
        if policy_root_hash is not None:
            rec["policy_root_hash"] = policy_root_hash
        etype = rec.get("entity_type", "entity")
        eid = rec.get("specimen_id") or rec.get("result_id")
        eid_str = _safe_filename(str(eid)) if eid is not None else "unknown"
        name = f"receipt_{etype}_{eid_str}.v0.1.json"
        p = bundle_dir / name
        p.write_text(_canonical_json(rec) + "\n", encoding="utf-8")
        written_files.append(name)

    # episode_log_subset.jsonl: all entries (subset = full for single-episode log)
    subset_path = bundle_dir / "episode_log_subset.jsonl"
    with subset_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(_canonical_json(e) + "\n")
    written_files.append("episode_log_subset.jsonl")

    # invariant_eval_trace.jsonl: one line per step with violations (t_s, step_index, violations)
    trace_path = bundle_dir / "invariant_eval_trace.jsonl"
    with trace_path.open("w", encoding="utf-8") as f:
        for i, e in enumerate(entries):
            v = e.get("violations")
            if v:
                row = {"step_index": i, "t_s": e.get("t_s"), "violations": v}
                f.write(_canonical_json(row) + "\n")
    written_files.append("invariant_eval_trace.jsonl")

    # enforcement_actions.jsonl: one line per step with enforcements
    enf_path = bundle_dir / "enforcement_actions.jsonl"
    with enf_path.open("w", encoding="utf-8") as f:
        for i, e in enumerate(entries):
            enfs = e.get("enforcements")
            if enfs:
                for enf in enfs:
                    row = {"step_index": i, "t_s": e.get("t_s"), **enf}
                    f.write(_canonical_json(row) + "\n")
    written_files.append("enforcement_actions.jsonl")

    # hashchain_proof.json
    hc = _hashchain_from_entries(entries)
    proof_path = bundle_dir / "hashchain_proof.json"
    proof_path.write_text(_canonical_json(hc) + "\n", encoding="utf-8")
    written_files.append("hashchain_proof.json")

    # manifest: policy_fingerprint (combined with tool_registry + rbac when present), optional fingerprints
    effective_policy_fp = combined_policy_fingerprint(
        policy_fingerprint or "",
        tool_registry_fingerprint,
        rbac_policy_fingerprint,
    )
    manifest: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "files": [],
        "policy_fingerprint": effective_policy_fp,
        "partner_id": partner_id,
        "policy_root_hash": policy_root_hash,
    }
    if tool_registry_fingerprint is not None:
        manifest["tool_registry_fingerprint"] = tool_registry_fingerprint
    if rbac_policy_fingerprint is not None:
        manifest["rbac_policy_fingerprint"] = rbac_policy_fingerprint
    if sign_bundle:
        manifest["signature"] = {"algorithm": "stub", "value": ""}
    else:
        manifest["signature"] = None

    for rel in sorted(written_files):
        full = bundle_dir / rel
        if full.exists():
            manifest["files"].append({"path": rel, "sha256": _sha256_file(full)})

    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(_canonical_json(manifest) + "\n", encoding="utf-8")

    return bundle_dir


def export_receipts(
    run_path: Path,
    out_dir: Path,
    policy_fingerprint: str | None = None,
    partner_id: str | None = None,
    policy_root: Path | None = None,
    tool_registry_fingerprint: str | None = None,
    rbac_policy_fingerprint: str | None = None,
) -> Path:
    """
    Load episode log from run_path (JSONL), build receipts, write EvidenceBundle.v0.1 to out_dir.
    When policy_root and partner_id are set, includes policy_pack_manifest.v0.1.json and
    policy_root_hash on manifest and each receipt.
    Returns path to EvidenceBundle.v0.1 directory.
    """
    entries = load_episode_log(run_path)
    if not entries:
        # No entities => one synthetic receipt for the run (decision BLOCKED, empty)
        hc = {
            "head_hash": "",
            "last_event_hash": "",
            "length": 0,
            "break_status": "intact",
        }
        receipts: list[dict[str, Any]] = [
            {
                "version": RECEIPT_VERSION,
                "entity_type": "specimen",
                "specimen_id": None,
                "result_id": None,
                "accession_ids": [],
                "panel_id": None,
                "device_ids": [],
                "timestamps": {},
                "decision": "BLOCKED",
                "reason_codes": [],
                "tokens": {"minted": [], "consumed": [], "revoked": []},
                "critical_comm_records": {"attempts": [], "ack_summary": []},
                "invariant_summary": {
                    "violated_ids": [],
                    "first_violation_ts": None,
                    "final_status": "PASS",
                },
                "enforcement_summary": {
                    "throttle": [],
                    "kill_switch": [],
                    "freeze_zone": [],
                    "forensic_freeze": [],
                },
                "hashchain": hc,
            }
        ]
    else:
        receipts = build_receipts_from_log(entries)
    pf = policy_fingerprint or (entries[0].get("policy_fingerprint") if entries else None)
    pid = partner_id or (entries[0].get("partner_id") if entries else None)
    tr_fp = tool_registry_fingerprint or (entries[0].get("tool_registry_fingerprint") if entries else None)
    rbac_fp = rbac_policy_fingerprint or (entries[0].get("rbac_policy_fingerprint") if entries else None)
    return write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint=pf,
        partner_id=pid,
        policy_root=policy_root,
        tool_registry_fingerprint=tr_fp,
        rbac_policy_fingerprint=rbac_fp,
    )
