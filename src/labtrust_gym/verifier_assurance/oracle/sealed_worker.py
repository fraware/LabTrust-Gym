"""
Durable sealed IPC worker for release-grade V_hidden isolation (LT-VA-02).

Public surfaces receive commitments only until an explicit freeze. The worker
process never imports policy/attacker modules and rejects sealed-frame payloads
that attempt to inject code references or hidden-label fields.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from labtrust_gym.verifier_assurance.oracle.dual_oracle import (
    CLAIM_BOUNDARY,
    HiddenOracle,
    LabelCommitment,
    OracleBoundaryError,
    default_hidden_profile,
    deny_hidden_in_mapping,
    seal_commitment,
)

PROTOCOL_VERSION = 1
FORBIDDEN_PAYLOAD_KEYS = (
    "policy_module",
    "attacker",
    "attacker_module",
    "hidden_adjudication",
    "ground_truth_label",
    "hidden_label",
)


def _frame_encode(obj: Mapping[str, Any]) -> bytes:
    raw = json.dumps(dict(obj), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{len(raw)}\n".encode("ascii") + raw + b"\n"


def _readline_bytes(stream: BinaryIO) -> bytes:
    buf = bytearray()
    while True:
        ch = stream.read(1)
        if not ch:
            break
        buf.extend(ch)
        if ch == b"\n":
            break
    return bytes(buf)


def _frame_read(stream: BinaryIO) -> dict[str, Any]:
    header = _readline_bytes(stream)
    if not header:
        raise OracleBoundaryError("sealed IPC closed unexpectedly")
    try:
        n = int(header.strip())
    except ValueError as exc:
        raise OracleBoundaryError(f"invalid sealed frame header: {header!r}") from exc
    if n < 0 or n > 16_000_000:
        raise OracleBoundaryError("sealed frame length out of bounds")
    payload = stream.read(n)
    if len(payload) != n:
        raise OracleBoundaryError("truncated sealed frame")
    trail = stream.read(1)
    if trail not in (b"\n", b""):
        raise OracleBoundaryError("sealed frame missing terminator")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OracleBoundaryError("sealed frame is not JSON") from exc
    if not isinstance(data, dict):
        raise OracleBoundaryError("sealed frame must be an object")
    return data


def _reject_forbidden(payload: Mapping[str, Any], *, path: str = "root") -> None:
    for k, v in payload.items():
        key = str(k)
        lower = key.lower()
        if key in FORBIDDEN_PAYLOAD_KEYS or any(
            f in lower for f in ("hidden_label", "ground_truth", "policy_module")
        ):
            raise OracleBoundaryError(f"forbidden sealed payload key at {path}.{key}")
        if isinstance(v, Mapping):
            _reject_forbidden(v, path=f"{path}.{key}")
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, Mapping):
                    _reject_forbidden(item, path=f"{path}.{key}[{i}]")


def _public_commitment_dict(c: LabelCommitment) -> dict[str, Any]:
    out = c.to_public_dict()
    deny_hidden_in_mapping(out)
    return out


@dataclass
class _WorkerState:
    campaign_id: str
    session_id: str
    freeze_token: str
    hidden: HiddenOracle
    commitments: list[LabelCommitment] = field(default_factory=list)
    frozen: bool = False


def run_sealed_worker_stdio(
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
) -> int:
    """
    Durable worker entry: length-prefixed JSON over binary stdio.
    Intended to run in a fresh interpreter with no policy imports.
    """
    inn = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout.buffer
    state: _WorkerState | None = None

    def reply(obj: Mapping[str, Any]) -> None:
        deny_hidden_in_mapping(obj, path="ipc_response")
        out.write(_frame_encode(obj))
        out.flush()

    while True:
        try:
            req = _frame_read(inn)
        except OracleBoundaryError as exc:
            reply({"ok": False, "error": str(exc), "claim_boundary": CLAIM_BOUNDARY})
            return 1
        try:
            _reject_forbidden(req)
            op = str(req.get("op") or "")
            if op == "hello":
                if int(req.get("protocol") or 0) != PROTOCOL_VERSION:
                    raise OracleBoundaryError("unsupported sealed protocol version")
                campaign_id = str(req.get("campaign_id") or "va-campaign")
                profile = req.get("hidden_profile") or default_hidden_profile()
                if not isinstance(profile, dict):
                    raise OracleBoundaryError("hidden_profile must be an object")
                state = _WorkerState(
                    campaign_id=campaign_id,
                    session_id=secrets.token_hex(16),
                    freeze_token=secrets.token_hex(16),
                    hidden=HiddenOracle(profile),
                )
                reply(
                    {
                        "ok": True,
                        "op": "hello",
                        "protocol": PROTOCOL_VERSION,
                        "session_id": state.session_id,
                        # freeze_token is returned only to the trusted parent, not public surfaces
                        "freeze_token": state.freeze_token,
                        "campaign_id": campaign_id,
                        "claim_boundary": CLAIM_BOUNDARY,
                    }
                )
                continue
            if state is None:
                raise OracleBoundaryError("sealed worker not initialized; send hello first")
            if req.get("session_id") != state.session_id:
                raise OracleBoundaryError("session_id mismatch")
            if op == "ping":
                reply({"ok": True, "op": "ping", "claim_boundary": CLAIM_BOUNDARY})
            elif op == "seal":
                if state.frozen:
                    raise OracleBoundaryError("campaign already frozen")
                episode_id = str(req.get("episode_id") or "")
                full_state = req.get("full_state")
                if not episode_id or not isinstance(full_state, dict):
                    raise OracleBoundaryError("seal requires episode_id and full_state object")
                deny_hidden_in_mapping(full_state, path="full_state")
                adjudication = state.hidden.adjudicate(full_state)
                commitment = seal_commitment(
                    adjudication,
                    campaign_id=state.campaign_id,
                    episode_id=episode_id,
                )
                state.commitments.append(commitment)
                reply({"ok": True, "op": "seal", "commitment": _public_commitment_dict(commitment)})
            elif op == "public_commitments":
                reply(
                    {
                        "ok": True,
                        "op": "public_commitments",
                        "commitments": [_public_commitment_dict(c) for c in state.commitments],
                    }
                )
            elif op == "freeze_reveal":
                if req.get("freeze_token") != state.freeze_token:
                    raise OracleBoundaryError("invalid freeze_token")
                state.frozen = True
                reveals = [c.reveal() for c in state.commitments]
                # Reveal path intentionally includes adjudication after freeze.
                out.write(
                    _frame_encode(
                        {
                            "ok": True,
                            "op": "freeze_reveal",
                            "reveals": reveals,
                            "claim_boundary": CLAIM_BOUNDARY,
                        }
                    )
                )
                out.flush()
            elif op == "shutdown":
                reply({"ok": True, "op": "shutdown", "claim_boundary": CLAIM_BOUNDARY})
                return 0
            else:
                raise OracleBoundaryError(f"unknown sealed op: {op}")
        except OracleBoundaryError as exc:
            reply({"ok": False, "error": str(exc), "claim_boundary": CLAIM_BOUNDARY})
            continue


class DurableSealedHiddenWorker:
    """
    Parent-side handle for a durable sealed hidden-oracle subprocess.

    Release-grade campaigns should use this instead of one-shot subprocess -c.
    CI may still use the in-process DualOracleBoundary façade.
    """

    def __init__(self, campaign_id: str = "va-campaign-release") -> None:
        self.campaign_id = campaign_id
        self._proc: subprocess.Popen[bytes] | None = None
        self._session_id: str | None = None
        self._freeze_token: str | None = None
        self._lock = threading.Lock()
        self._closed = False

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def start(self, *, hidden_profile: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if self._proc is not None:
            raise OracleBoundaryError("durable worker already started")
        cmd = [
            sys.executable,
            "-c",
            "from labtrust_gym.verifier_assurance.oracle.sealed_worker import run_sealed_worker_stdio; "
            "raise SystemExit(run_sealed_worker_stdio())",
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        hello = {
            "op": "hello",
            "protocol": PROTOCOL_VERSION,
            "campaign_id": self.campaign_id,
            "hidden_profile": dict(hidden_profile or default_hidden_profile()),
        }
        resp = self._transact(hello, expect_session=False)
        self._session_id = str(resp["session_id"])
        self._freeze_token = str(resp["freeze_token"])
        return {
            "ok": True,
            "session_id": self._session_id,
            "campaign_id": self.campaign_id,
            "protocol": PROTOCOL_VERSION,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    def _transact(self, req: dict[str, Any], *, expect_session: bool = True) -> dict[str, Any]:
        with self._lock:
            if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
                raise OracleBoundaryError("durable worker not running")
            if expect_session:
                if not self._session_id:
                    raise OracleBoundaryError("missing session_id")
                req = {**req, "session_id": self._session_id}
            _reject_forbidden(req)
            self._proc.stdin.write(_frame_encode(req))
            self._proc.stdin.flush()
            resp = _frame_read(self._proc.stdout)
            if not resp.get("ok"):
                raise OracleBoundaryError(str(resp.get("error") or "sealed worker error"))
            if resp.get("op") != "freeze_reveal":
                deny_hidden_in_mapping(resp, path="ipc_response")
            return resp

    def ping(self) -> dict[str, Any]:
        return self._transact({"op": "ping"})

    def seal_episode(self, full_state: Mapping[str, Any], episode_id: str) -> dict[str, Any]:
        resp = self._transact(
            {
                "op": "seal",
                "episode_id": episode_id,
                "full_state": dict(full_state),
            }
        )
        commitment = resp["commitment"]
        deny_hidden_in_mapping(commitment)
        if "adjudication" in commitment:
            raise OracleBoundaryError("sealed worker leaked adjudication into public commitment")
        return dict(commitment)

    def public_commitments(self) -> list[dict[str, Any]]:
        resp = self._transact({"op": "public_commitments"})
        commits = list(resp.get("commitments") or [])
        for c in commits:
            deny_hidden_in_mapping(c)
        return commits

    def freeze_and_reveal(self) -> list[dict[str, Any]]:
        if not self._freeze_token:
            raise OracleBoundaryError("missing freeze_token")
        resp = self._transact({"op": "freeze_reveal", "freeze_token": self._freeze_token})
        return list(resp.get("reveals") or [])

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    self._transact({"op": "shutdown"})
                except OracleBoundaryError:
                    pass
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
        finally:
            self._proc = None

    def __enter__(self) -> DurableSealedHiddenWorker:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.shutdown()


def sealed_worker_module_path() -> Path:
    return Path(__file__).resolve()


def fingerprint_worker_image() -> str:
    """Digest of worker module bytes for release provenance (not a secret)."""
    data = sealed_worker_module_path().read_bytes()
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    raise SystemExit(run_sealed_worker_stdio())
