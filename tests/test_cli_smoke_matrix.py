"""
CLI smoke matrix: run each README-listed CLI command with minimal args, assert exit 0 and expected outputs.

Uses subprocess (python -m labtrust_gym.cli.main). Timeouts and output checks align with
docs/cli_contract.md. Commands requiring [marl] or long-running (serve) are skipped unless
LABTRUST_CLI_FULL=1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

# Timeout tiers (seconds) per docs/cli_contract.md: light 30s, medium 60–90s, heavy 120–360s.
TIMEOUT_FAST = 30
TIMEOUT_MEDIUM = 90
TIMEOUT_HEAVY = 180
TIMEOUT_COORD_PACK = 300
TIMEOUT_FORKER = 360

# Minimal two-step episode JSONL for receipt/bundle tests (hashchain-compatible).
_MINIMAL_EPISODE_JSONL = (
    '{"t_s":100,"agent_id":"A","action_type":"CREATE_ACCESSION","args":{"specimen_id":"S1"},"status":"ACCEPTED",'
    '"hashchain":{"head_hash":"h0","length":1,"last_event_hash":"e0"}}\n'
    '{"t_s":200,"agent_id":"A","action_type":"ACCEPT_SPECIMEN","args":{"specimen_id":"S1"},"status":"ACCEPTED",'
    '"hashchain":{"head_hash":"h1","length":2,"last_event_hash":"e1"}}\n'
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_labtrust(
    args: list[str],
    cwd: Path | None = None,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run labtrust CLI via python -m labtrust_gym.cli.main."""
    root = cwd or _repo_root()
    env = {**os.environ, **(env or {})}
    cmd = [sys.executable, "-m", "labtrust_gym.cli.main"] + args
    return subprocess.run(
        cmd,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _assert_cli_success(proc: subprocess.CompletedProcess[str], command_hint: str = "") -> None:
    """Assert CLI process exited 0; raise with stderr and hint if not."""
    if proc.returncode == 0:
        return
    hint = f" [{command_hint}]" if command_hint else ""
    msg = f"labtrust{hint} exited {proc.returncode}; stderr={proc.stderr!r}; stdout={proc.stdout!r}"
    raise AssertionError(msg)


def _write_minimal_episode_log(path: Path) -> None:
    """Write minimal two-step episode JSONL to path (for receipt/bundle tests)."""
    path.write_text(_MINIMAL_EPISODE_JSONL, encoding="utf-8")


def test_cli_validate_policy() -> None:
    """validate-policy: exit 0, no output files."""
    r = _run_labtrust(["validate-policy"], timeout=TIMEOUT_FAST)
    _assert_cli_success(r, "validate-policy")


def test_cli_run_benchmark(tmp_path: Path) -> None:
    """run-benchmark: 1 episode, results.json exists and has task/episodes."""
    out = tmp_path / "results.json"
    r = _run_labtrust(
        [
            "run-benchmark",
            "--task",
            "throughput_sla",
            "--episodes",
            "1",
            "--seed",
            "42",
            "--out",
            str(out),
        ],
        timeout=TIMEOUT_MEDIUM,
    )
    _assert_cli_success(r)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data.get("task") == "throughput_sla"
    assert data.get("num_episodes") == 1
    assert "episodes" in data and len(data["episodes"]) == 1


def test_cli_eval_agent(tmp_path: Path) -> None:
    """eval-agent: external agent, results.json v0.2."""
    out = tmp_path / "results.json"
    r = _run_labtrust(
        [
            "eval-agent",
            "--task",
            "throughput_sla",
            "--episodes",
            "1",
            "--agent",
            "examples.external_agent_demo:SafeNoOpAgent",
            "--out",
            str(out),
            "--seed",
            "42",
        ],
        timeout=TIMEOUT_MEDIUM,
    )
    _assert_cli_success(r)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "schema_version" in data and data["schema_version"] == "0.2"
    assert "episodes" in data


def test_cli_bench_smoke() -> None:
    """bench-smoke: 1 episode per task (throughput_sla, stat_insertion, qc_cascade); exit 0."""
    r = _run_labtrust(["bench-smoke", "--seed", "42"], timeout=90)
    _assert_cli_success(r)
    assert "bench-smoke all tasks OK" in r.stderr or "OK" in r.stderr


def test_cli_quick_eval(tmp_path: Path) -> None:
    """quick-eval: 1 ep per task, run dir with throughput_sla.json and summary.md."""
    out_dir = tmp_path / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        ["quick-eval", "--seed", "42", "--out-dir", str(out_dir)],
        timeout=TIMEOUT_MEDIUM,
    )
    _assert_cli_success(r)
    run_dirs = [d for d in out_dir.iterdir() if d.is_dir() and d.name.startswith("quick_eval_")]
    assert len(run_dirs) >= 1
    run_dir = run_dirs[0]
    assert (run_dir / "throughput_sla.json").exists()
    assert (run_dir / "adversarial_disruption.json").exists()
    assert (run_dir / "multi_site_stat.json").exists()
    assert (run_dir / "summary.md").exists()


def test_cli_export_receipts(tmp_path: Path) -> None:
    """export-receipts: need episode log JSONL; writes EvidenceBundle.v0.1."""
    root = _repo_root()
    log_path = tmp_path / "episodes.jsonl"
    _write_minimal_episode_log(log_path)
    out_dir = tmp_path / "receipts_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        ["export-receipts", "--run", str(log_path), "--out", str(out_dir)],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r, "export-receipts")
    bundle = out_dir / "EvidenceBundle.v0.1"
    assert bundle.is_dir()
    assert (bundle / "manifest.json").exists()


def test_cli_export_fhir(tmp_path: Path) -> None:
    """export-fhir: receipts dir = EvidenceBundle.v0.1; writes fhir_bundle.json."""
    root = _repo_root()
    receipts = root / "tests" / "fixtures" / "ui_fixtures" / "evidence_bundle" / "EvidenceBundle.v0.1"
    if not receipts.is_dir():
        pytest.skip("tests/fixtures/ui_fixtures/evidence_bundle/EvidenceBundle.v0.1 not found")
    out_dir = tmp_path / "fhir_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        ["export-fhir", "--receipts", str(receipts), "--out", str(out_dir)],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r)
    assert (out_dir / "fhir_bundle.json").exists()


def test_cli_verify_bundle(tmp_path: Path) -> None:
    """verify-bundle: EvidenceBundle.v0.1 dir; exit 0 and PASS. Use a freshly built bundle so hashes match."""
    from labtrust_gym.export.receipts import (
        build_receipts_from_log,
        load_episode_log,
        write_evidence_bundle,
    )

    root = _repo_root()
    log_path = tmp_path / "episodes.jsonl"
    _write_minimal_episode_log(log_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "bundle_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(out_dir, receipts, entries, policy_fingerprint="fp_smoke", partner_id=None)
    r = _run_labtrust(["verify-bundle", "--bundle", str(bundle_dir)], cwd=root, timeout=30)
    _assert_cli_success(r)
    assert "PASS" in r.stderr or "PASS" in r.stdout


def test_cli_verify_release(tmp_path: Path) -> None:
    """verify-release: minimal release dir with receipts/<task>/EvidenceBundle.v0.1 (fresh bundle so hashes match)."""
    from labtrust_gym.export.receipts import (
        build_receipts_from_log,
        load_episode_log,
        write_evidence_bundle,
    )

    root = _repo_root()
    log_path = tmp_path / "episodes.jsonl"
    _write_minimal_episode_log(log_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    release_dir = tmp_path / "release"
    receipts_task = release_dir / "receipts" / "throughput_sla"
    receipts_task.mkdir(parents=True, exist_ok=True)
    write_evidence_bundle(receipts_task, receipts, entries, policy_fingerprint="fp_smoke", partner_id=None)
    r = _run_labtrust(
        ["verify-release", "--release-dir", str(release_dir)],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r)


def test_cli_run_security_suite(tmp_path: Path) -> None:
    """run-security-suite: smoke, SECURITY/attack_results.json."""
    r = _run_labtrust(
        ["run-security-suite", "--out", str(tmp_path / "sec"), "--smoke", "--seed", "42"],
        timeout=TIMEOUT_MEDIUM,
    )
    _assert_cli_success(r)
    sec_dir = tmp_path / "sec" / "SECURITY"
    assert sec_dir.is_dir()
    assert (sec_dir / "attack_results.json").exists()


def test_cli_safety_case(tmp_path: Path) -> None:
    """safety-case: SAFETY_CASE/safety_case.json and .md."""
    out_dir = tmp_path / "safety_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(["safety-case", "--out", str(out_dir)], timeout=30)
    _assert_cli_success(r)
    sc = out_dir / "SAFETY_CASE"
    assert sc.is_dir()
    assert (sc / "safety_case.json").exists()
    assert (sc / "safety_case.md").exists()


def test_cli_ui_export(tmp_path: Path) -> None:
    """ui-export: run dir from quick-eval; zip with index.json. Requires throughput_sla.json + logs/."""
    root = _repo_root()
    # Create minimal quick-eval-like layout (throughput_sla.json + logs/ required by _detect_run_type)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "throughput_sla.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "task": "throughput_sla",
                "num_episodes": 1,
                "seeds": [42],
                "episodes": [{"seed": 42, "metrics": {"throughput": 1, "steps": 10}}],
                "agent_baseline_id": "scripted_ops_v1",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "adversarial_disruption.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "task": "adversarial_disruption",
                "num_episodes": 1,
                "seeds": [42],
                "episodes": [{"seed": 42, "metrics": {"containment_success": True}}],
                "agent_baseline_id": "scripted_ops_v1",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "multi_site_stat.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "task": "multi_site_stat",
                "num_episodes": 1,
                "seeds": [42],
                "episodes": [{"seed": 42, "metrics": {}}],
                "agent_baseline_id": "scripted_ops_v1",
            }
        ),
        encoding="utf-8",
    )
    zip_path = tmp_path / "ui_bundle.zip"
    r = _run_labtrust(
        ["ui-export", "--run", str(run_dir), "--out", str(zip_path)],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r)
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
    assert any("index.json" in n for n in names)


def test_cli_export_risk_register(tmp_path: Path) -> None:
    """export-risk-register: --out and optional --runs; RISK_REGISTER_BUNDLE.v0.1.json."""
    root = _repo_root()
    out_dir = tmp_path / "risk_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        ["export-risk-register", "--out", str(out_dir), "--runs", "tests/fixtures/ui_fixtures"],
        cwd=root,
        timeout=TIMEOUT_MEDIUM,
    )
    _assert_cli_success(r)
    bundle_file = out_dir / "RISK_REGISTER_BUNDLE.v0.1.json"
    assert bundle_file.exists()


def test_cli_build_risk_register_bundle(tmp_path: Path) -> None:
    """build-risk-register-bundle: --out path, JSON file."""
    root = _repo_root()
    out_path = tmp_path / "risk_register_bundle.v0.1.json"
    r = _run_labtrust(
        ["build-risk-register-bundle", "--out", str(out_path)],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r)
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "schema_version" in data or "risks" in data or "evidence" in data


def test_cli_summarize_results(tmp_path: Path) -> None:
    """summarize-results: --in results path, summary_v0.2.csv and summary.md in --out."""
    root = _repo_root()
    in_file = root / "tests" / "fixtures" / "ui_fixtures" / "results_v0.2.json"
    if not in_file.exists():
        pytest.skip("tests/fixtures/ui_fixtures/results_v0.2.json not found")
    out_dir = tmp_path / "summary_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        [
            "summarize-results",
            "--in",
            str(in_file),
            "--out",
            str(out_dir),
            "--basename",
            "summary",
        ],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r)
    assert (out_dir / "summary_v0.2.csv").exists()
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "summary.md").exists()


def test_cli_determinism_report(tmp_path: Path) -> None:
    """determinism-report: 2 episodes, determinism_report.json and .md."""
    r = _run_labtrust(
        [
            "determinism-report",
            "--task",
            "throughput_sla",
            "--episodes",
            "2",
            "--seed",
            "42",
            "--out",
            str(tmp_path / "det_out"),
        ],
        timeout=TIMEOUT_MEDIUM,
    )
    _assert_cli_success(r)
    out_dir = tmp_path / "det_out"
    assert (out_dir / "determinism_report.json").exists()
    assert (out_dir / "determinism_report.md").exists()


@pytest.mark.slow
def test_cli_forker_quickstart(tmp_path: Path) -> None:
    """forker-quickstart: pack + report + risk register under --out. Long-running (~3–5 min)."""
    out_dir = tmp_path / "forker_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        ["forker-quickstart", "--out", str(out_dir)],
        timeout=TIMEOUT_FORKER,
    )
    _assert_cli_success(r)
    pack_dir = out_dir / "pack"
    assert pack_dir.is_dir()
    assert (pack_dir / "pack_summary.csv").exists()
    assert (pack_dir / "COORDINATION_DECISION.v0.1.json").exists()
    risk_out = out_dir / "risk_out"
    assert (risk_out / "RISK_REGISTER_BUNDLE.v0.1.json").exists()


@pytest.mark.slow
def test_cli_run_coordination_security_pack(tmp_path: Path) -> None:
    """run-coordination-security-pack: pack_summary.csv, pack_gate.md. Long-running (~3–4 min)."""
    r = _run_labtrust(
        [
            "run-coordination-security-pack",
            "--out",
            str(tmp_path / "pack_out"),
            "--seed",
            "42",
        ],
        timeout=TIMEOUT_COORD_PACK,
    )
    _assert_cli_success(r)
    out = tmp_path / "pack_out"
    assert (out / "pack_summary.csv").exists()
    assert (out / "pack_gate.md").exists()


def test_cli_summarize_coordination(tmp_path: Path) -> None:
    """summarize-coordination: --in has summary_coord.csv, --out has summary/sota_leaderboard.csv."""
    root = _repo_root()
    in_dir = root / "tests" / "fixtures" / "coordination_matrix_run_fixture"
    if not (in_dir / "summary_coord.csv").exists():
        in_dir_alt = in_dir / "summary"
        if in_dir_alt.exists() and (in_dir_alt / "summary_coord.csv").exists():
            in_dir = in_dir_alt
        else:
            pytest.skip("fixture summary_coord.csv not found")
    out_dir = tmp_path / "coord_summary_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        ["summarize-coordination", "--in", str(in_dir), "--out", str(out_dir)],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r)
    assert (out_dir / "summary" / "sota_leaderboard.csv").exists()


def test_cli_recommend_coordination_method(tmp_path: Path) -> None:
    """recommend-coordination-method: run dir with pack_summary or summary_coord; COORDINATION_DECISION."""
    root = _repo_root()
    run_dir = root / "tests" / "fixtures" / "coordination_matrix_run_fixture"
    if not run_dir.is_dir():
        pytest.skip("coordination_matrix_run_fixture not found")
    out_dir = tmp_path / "decision_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        ["recommend-coordination-method", "--run", str(run_dir), "--out", str(out_dir)],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r)
    assert (out_dir / "COORDINATION_DECISION.v0.1.json").exists()
    assert (out_dir / "COORDINATION_DECISION.md").exists()


def test_cli_build_coordination_matrix(tmp_path: Path) -> None:
    """build-coordination-matrix: run dir with summary; coordination_matrix.v0.1.json."""
    root = _repo_root()
    run_dir = root / "tests" / "fixtures" / "coordination_matrix_run_fixture"
    if not run_dir.is_dir():
        pytest.skip("coordination_matrix_run_fixture not found")
    r = _run_labtrust(
        [
            "build-coordination-matrix",
            "--run",
            str(run_dir),
            "--out",
            str(tmp_path),
            "--matrix-mode",
            "pack",
        ],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r)
    matrix_file = tmp_path / "coordination_matrix.v0.1.json"
    if not matrix_file.exists():
        matrix_file = tmp_path / "matrix.json"
    assert matrix_file.exists()


def test_cli_make_plots(tmp_path: Path) -> None:
    """make-plots: run dir from study (manifest.json at root, results/cond_*/results.json); figures/ created."""
    root = _repo_root()
    run_dir = tmp_path / "plot_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "condition_ids": ["cond_0"],
                "condition_labels": ["baseline"],
                "num_conditions": 1,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "results" / "cond_0").mkdir(parents=True, exist_ok=True)
    (run_dir / "results" / "cond_0" / "results.json").write_text(
        json.dumps(
            {
                "task": "throughput_sla",
                "num_episodes": 1,
                "episodes": [{"seed": 42, "metrics": {"throughput": 5, "steps": 50}}],
                "agent_baseline_id": "scripted_ops_v1",
            }
        ),
        encoding="utf-8",
    )
    r = _run_labtrust(["make-plots", "--run", str(run_dir)], cwd=root, timeout=60)
    _assert_cli_success(r)
    figures = run_dir / "figures"
    assert figures.is_dir()


@pytest.mark.slow
def test_cli_reproduce_minimal(tmp_path: Path) -> None:
    """reproduce --profile minimal: sweep dirs and figures."""
    out_dir = tmp_path / "repro_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "LABTRUST_REPRO_SMOKE": "1"}
    r = _run_labtrust(
        ["reproduce", "--profile", "minimal", "--out", str(out_dir)],
        timeout=TIMEOUT_HEAVY,
        env=env,
    )
    _assert_cli_success(r)
    assert (out_dir / "throughput_sla").is_dir()
    assert (out_dir / "qc_cascade").is_dir()
    assert (out_dir / "throughput_sla" / "figures").is_dir()


@pytest.mark.slow
def test_cli_package_release_minimal(tmp_path: Path) -> None:
    """package-release --profile minimal: MANIFEST, _repr, receipts."""
    out_dir = tmp_path / "release_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        [
            "package-release",
            "--profile",
            "minimal",
            "--out",
            str(out_dir),
            "--seed-base",
            "100",
        ],
        timeout=TIMEOUT_HEAVY,
    )
    _assert_cli_success(r)
    assert (out_dir / "MANIFEST.v0.1.json").exists() or (out_dir / "metadata.json").exists()
    repr_dir = out_dir / "_repr"
    assert repr_dir.is_dir() or (out_dir / "receipts").is_dir()


@pytest.mark.slow
def test_cli_run_official_pack_smoke(tmp_path: Path) -> None:
    """run-official-pack --smoke: pack_manifest or metadata, _baselines or SECURITY."""
    out_dir = tmp_path / "official_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "LABTRUST_OFFICIAL_PACK_SMOKE": "1"}
    r = _run_labtrust(
        ["run-official-pack", "--out", str(out_dir), "--smoke"],
        timeout=TIMEOUT_HEAVY,
        env=env,
    )
    _assert_cli_success(r)
    assert (out_dir / "metadata.json").exists() or (out_dir / "pack_manifest.json").exists()


@pytest.mark.slow
def test_cli_generate_official_baselines(tmp_path: Path) -> None:
    """generate-official-baselines: 2 episodes, --force; results/, summary.csv."""
    out_dir = tmp_path / "baselines_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        [
            "generate-official-baselines",
            "--out",
            str(out_dir),
            "--episodes",
            "2",
            "--seed",
            "42",
            "--force",
        ],
        timeout=TIMEOUT_HEAVY,
    )
    _assert_cli_success(r)
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "metadata.json").exists()


@pytest.mark.slow
def test_cli_run_study(tmp_path: Path) -> None:
    """run-study: spec YAML, out dir with manifest and results."""
    root = _repo_root()
    spec = root / "policy" / "studies" / "study_spec.example.v0.1.yaml"
    if not spec.exists():
        pytest.skip("policy/studies/study_spec.example.v0.1.yaml not found")
    out_dir = tmp_path / "study_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        ["run-study", "--spec", str(spec), "--out", str(out_dir)],
        cwd=root,
        timeout=TIMEOUT_HEAVY,
    )
    _assert_cli_success(r)
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "results").is_dir()


@pytest.mark.slow
def test_cli_run_coordination_study(tmp_path: Path) -> None:
    """run-coordination-study: smoke spec, summary_coord.csv and cells."""
    root = _repo_root()
    spec = root / "tests" / "fixtures" / "coordination_study_llm_smoke_spec.yaml"
    if not spec.exists():
        spec = root / "tests" / "fixtures" / "coordination_study_smoke_spec.yaml"
    if not spec.exists():
        pytest.skip("coordination study smoke spec not found")
    out_dir = tmp_path / "coord_study_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        [
            "run-coordination-study",
            "--spec",
            str(spec),
            "--out",
            str(out_dir),
            "--llm-backend",
            "deterministic",
        ],
        cwd=root,
        timeout=TIMEOUT_HEAVY,
    )
    _assert_cli_success(r)
    summary_csv = out_dir / "summary" / "summary_coord.csv"
    if not summary_csv.exists():
        summary_csv = out_dir / "summary_coord.csv"
    assert summary_csv.exists()


def test_cli_train_ppo_invalid_train_config(tmp_path: Path) -> None:
    """train-ppo with missing --train-config file exits 1 and reports error."""
    root = _repo_root()
    bad_path = tmp_path / "nonexistent_train_config.json"
    assert not bad_path.exists()
    r = _run_labtrust(
        ["train-ppo", "--train-config", str(bad_path), "--timesteps", "1", "--out", str(tmp_path / "out")],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    assert r.returncode != 0
    assert "not found" in (r.stderr + r.stdout).lower() or "Failed to load" in (r.stderr + r.stdout)


@pytest.mark.skipif(
    not os.environ.get("LABTRUST_CLI_FULL"),
    reason="LABTRUST_CLI_FULL not set; train-ppo requires [marl]",
)
@pytest.mark.slow
def test_cli_train_ppo(tmp_path: Path) -> None:
    """train-ppo: minimal timesteps; optional, requires [marl]."""
    out_dir = tmp_path / "ppo_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        [
            "train-ppo",
            "--task",
            "throughput_sla",
            "--timesteps",
            "100",
            "--seed",
            "42",
            "--out",
            str(out_dir),
        ],
        timeout=TIMEOUT_HEAVY,
    )
    _assert_cli_success(r)
    # May write model.zip or run dir
    assert out_dir.is_dir() and (list(out_dir.iterdir()) or (out_dir / "model.zip").exists())


@pytest.mark.skipif(
    not os.environ.get("LABTRUST_CLI_FULL"),
    reason="LABTRUST_CLI_FULL not set; eval-ppo requires [marl] and trained model",
)
def test_cli_eval_ppo(tmp_path: Path) -> None:
    """eval-ppo: requires trained model; skip unless LABTRUST_CLI_FULL and model present."""
    root = _repo_root()
    model = root / "runs" / "ppo" / "model.zip"
    if not model.exists():
        pytest.skip("No trained model at runs/ppo/model.zip")
    out_path = tmp_path / "eval_results.json"
    r = _run_labtrust(
        [
            "eval-ppo",
            "--model",
            str(model),
            "--task",
            "throughput_sla",
            "--episodes",
            "2",
            "--seed",
            "42",
            "--out",
            str(out_path),
        ],
        timeout=TIMEOUT_MEDIUM,
    )
    _assert_cli_success(r)


def test_cli_deps_inventory(tmp_path: Path) -> None:
    """deps-inventory: SECURITY/deps_inventory_runtime.json."""
    out_dir = tmp_path / "deps_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(["deps-inventory", "--out", str(out_dir)], timeout=30)
    _assert_cli_success(r)
    assert (out_dir / "SECURITY" / "deps_inventory_runtime.json").exists()


def test_cli_transparency_log(tmp_path: Path) -> None:
    """transparency-log: artifact with _repr and receipts; TRANSPARENCY_LOG/."""
    root = _repo_root()
    artifact = tmp_path / "artifact"
    artifact.mkdir(parents=True, exist_ok=True)
    repr_dir = artifact / "_repr" / "throughput_sla"
    repr_dir.mkdir(parents=True, exist_ok=True)
    (repr_dir / "results.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "task": "throughput_sla",
                "seeds": [42],
                "episodes": [{"seed": 42, "metrics": {"throughput": 5, "steps": 100}}],
                "agent_baseline_id": "scripted_ops_v1",
            }
        ),
        encoding="utf-8",
    )
    (repr_dir / "episodes.jsonl").write_text('{"action_type":"CREATE_ACCESSION","t_s":10}\n', encoding="utf-8")
    out_dir = tmp_path / "transparency_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = _run_labtrust(
        ["transparency-log", "--in", str(artifact), "--out", str(out_dir)],
        cwd=root,
        timeout=TIMEOUT_FAST,
    )
    _assert_cli_success(r)
    tl = out_dir / "TRANSPARENCY_LOG"
    assert tl.is_dir()
    assert (tl / "root.txt").exists() or (tl / "log.json").exists()
