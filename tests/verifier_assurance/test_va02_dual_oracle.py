"""LT-VA-02 dual oracle leakage and disagreement tests."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from labtrust_gym.verifier_assurance.oracle.dual_oracle import (
    OracleBoundaryError,
    PublicVerifier,
    SubprocessHiddenWorker,
    default_hidden_profile,
    default_public_profile,
    deny_hidden_in_mapping,
    make_inprocess_boundary,
    scan_filesystem_paths_for_leakage,
    scan_process_env_for_leakage,
)
from labtrust_gym.verifier_assurance.oracle.sealed_worker import (
    DurableSealedHiddenWorker,
    fingerprint_worker_image,
)


def _released_state(**extra):
    state = {
        "result_released": True,
        "qc": {
            "device_qc_state": {"D1": "pass"},
            "results": {"R1": {"status": "released", "flags": []}},
        },
        "specimens": {"S1": {"status": "accepted"}},
        "process": {},
        "authorization": {},
        "audit": {},
        "critical": {},
        "side_effects": {},
    }
    state.update(extra)
    return state


def test_public_hidden_disagreement_on_invalid_process() -> None:
    boundary = make_inprocess_boundary("camp-1")
    state = _released_state(process={"invalid_process": True, "invalid_process_reason": "qc_bypass"})
    public = boundary.evaluate_public(state)
    assert public.accepted is True  # terminal-only public
    commitment = boundary.seal_episode(state, "ep-1")
    assert "commitment" in commitment
    assert "adjudication" not in commitment
    reveals = boundary.freeze_and_reveal()
    assert reveals[0]["adjudication"]["accepted"] is False
    assert "VA_INVALID_PROCESS" in reveals[0]["adjudication"]["reason_codes"]


def test_hidden_attribute_api_denial() -> None:
    boundary = make_inprocess_boundary()
    with pytest.raises(OracleBoundaryError):
        _ = boundary.v_hidden  # type: ignore[attr-defined]
    with pytest.raises(OracleBoundaryError):
        _ = boundary.hidden_label  # type: ignore[attr-defined]


def test_observation_log_leakage_scan() -> None:
    obs = {"agent": {"queues": 1, "notes": "ok"}}
    deny_hidden_in_mapping(obs)
    with pytest.raises(OracleBoundaryError):
        deny_hidden_in_mapping({"info": {"hidden_label": "exploit"}})
    with pytest.raises(OracleBoundaryError):
        deny_hidden_in_mapping({"log": "ground_truth leaked"})


def test_exception_text_and_env_leakage(monkeypatch: pytest.MonkeyPatch) -> None:
    scan_process_env_for_leakage()
    monkeypatch.setenv("LABTRUST_VA_HIDDEN_LABEL", "secret")
    with pytest.raises(OracleBoundaryError):
        scan_process_env_for_leakage()


def test_filesystem_path_leakage_scan() -> None:
    scan_filesystem_paths_for_leakage(
        ["benchmarks/verifier_assurance/release_packs/labtrust-va-release-v1"]
    )
    with pytest.raises(OracleBoundaryError):
        scan_filesystem_paths_for_leakage(["/tmp/campaign/hidden_adjudication.json"])
    with pytest.raises(OracleBoundaryError):
        scan_filesystem_paths_for_leakage([r"C:\data\v_hidden\labels.json"])


def test_public_rejects_hidden_keys_in_state() -> None:
    pub = PublicVerifier(default_public_profile())
    with pytest.raises(OracleBoundaryError):
        pub.evaluate({"result_released": True, "hidden_label": "x"})


def test_subprocess_hidden_worker_contract() -> None:
    payload = {
        "hidden_profile": default_hidden_profile(),
        "full_state": _released_state(authorization={"unauthorized": True}),
    }
    out = SubprocessHiddenWorker.adjudicate_payload(json.dumps(payload))
    data = json.loads(out)
    assert data["accepted"] is False
    with pytest.raises(OracleBoundaryError):
        SubprocessHiddenWorker.adjudicate_payload(json.dumps({**payload, "policy_module": "evil"}))


def test_subprocess_isolation_fresh_interpreter() -> None:
    code = (
        "import json; from labtrust_gym.verifier_assurance.oracle.dual_oracle import "
        "SubprocessHiddenWorker, default_hidden_profile; "
        "payload={'hidden_profile': default_hidden_profile(), "
        "'full_state': {'result_released': True, 'qc': {'results': {'R1': {'status': 'released', 'flags': []}}, "
        "'device_qc_state': {}}, 'process': {'premature_release': True}, 'authorization': {}, "
        "'audit': {}, 'critical': {}, 'side_effects': {}}}; "
        "print(SubprocessHiddenWorker.adjudicate_payload(json.dumps(payload)))"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout.strip())
    assert data["accepted"] is False


def test_durable_sealed_worker_commitments_until_freeze() -> None:
    assert len(fingerprint_worker_image()) == 64
    worker = DurableSealedHiddenWorker(campaign_id="camp-durable")
    try:
        started = worker.start()
        assert "freeze_token" not in started
        assert started["session_id"]
        worker.ping()
        state = _released_state(process={"invalid_process": True})
        commit = worker.seal_episode(state, "ep-durable-1")
        assert "adjudication" not in commit
        assert commit["revealed"] is False
        deny_hidden_in_mapping(commit)
        publics = worker.public_commitments()
        assert len(publics) == 1
        deny_hidden_in_mapping(publics)
        reveals = worker.freeze_and_reveal()
        assert reveals[0]["adjudication"]["accepted"] is False
        with pytest.raises(OracleBoundaryError):
            worker.seal_episode(state, "ep-after-freeze")
    finally:
        worker.shutdown()


def test_durable_sealed_worker_rejects_policy_injection() -> None:
    worker = DurableSealedHiddenWorker(campaign_id="camp-inject")
    try:
        worker.start()
        with pytest.raises(OracleBoundaryError):
            worker._transact({"op": "ping", "policy_module": "evil"})
    finally:
        worker.shutdown()
