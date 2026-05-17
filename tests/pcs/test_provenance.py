"""PCS provenance and deterministic fixture behavior."""

from __future__ import annotations

import subprocess

from labtrust_gym.pcs.deterministic import DETERMINISTIC_SOURCE_COMMIT, deterministic_mode
from labtrust_gym.pcs.provenance import LOCAL_DEV_COMMIT, base_provenance, resolve_source_commit


def test_resolve_source_commit_local_dev_when_no_git(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    commit, local_dev = resolve_source_commit()
    assert commit == LOCAL_DEV_COMMIT
    assert local_dev is True
    fields = base_provenance()
    assert fields["source_commit"] == LOCAL_DEV_COMMIT
    assert fields.get("local_dev") is True


def test_deterministic_mode_freezes_source_commit(monkeypatch) -> None:
    monkeypatch.delenv("PCS_DETERMINISTIC", raising=False)
    with deterministic_mode():
        commit, local_dev = resolve_source_commit()
        assert commit == DETERMINISTIC_SOURCE_COMMIT
        assert local_dev is False
        fields = base_provenance()
        assert fields["source_commit"] == DETERMINISTIC_SOURCE_COMMIT
        assert "local_dev" not in fields
