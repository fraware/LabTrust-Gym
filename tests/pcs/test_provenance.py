"""PCS provenance and deterministic fixture behavior."""

from __future__ import annotations

from labtrust_gym.pcs.deterministic import DETERMINISTIC_SOURCE_COMMIT, deterministic_mode
from labtrust_gym.pcs.provenance import LOCAL_DEV_COMMIT, base_provenance, resolve_source_commit


def test_resolve_source_commit_local_dev_when_no_git(monkeypatch) -> None:
    monkeypatch.delenv("PCS_DETERMINISTIC", raising=False)
    monkeypatch.setattr(
        "labtrust_gym.pcs.provenance._read_git_head",
        lambda _cwd: None,
    )
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


def test_local_dev_commit_marker_valid_only_with_local_dev_true(monkeypatch) -> None:
    monkeypatch.delenv("PCS_DETERMINISTIC", raising=False)
    monkeypatch.setattr(
        "labtrust_gym.pcs.provenance._read_git_head",
        lambda _cwd: None,
    )
    commit, local_dev = resolve_source_commit()
    fields = base_provenance()
    assert local_dev is True
    assert commit == LOCAL_DEV_COMMIT
    assert fields.get("local_dev") is True
    assert fields["source_commit"] == LOCAL_DEV_COMMIT

    monkeypatch.delenv("PCS_DETERMINISTIC", raising=False)
    with deterministic_mode():
        commit2, local_dev2 = resolve_source_commit()
        fields2 = base_provenance()
    assert local_dev2 is False
    assert "local_dev" not in fields2
    assert commit2 != LOCAL_DEV_COMMIT
    assert fields2["source_commit"] == commit2
