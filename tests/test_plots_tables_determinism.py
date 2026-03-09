"""
Plotting pipeline: data tables (CSV) must be identical across runs for same study output.
Generates plots for a tiny study run and asserts CSV tables match (determinism).
"""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

from labtrust_gym.studies.plots import (
    get_data_table_paths,
    make_plots,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _minimal_study_run(tmp_path: Path) -> Path:
    """Create a minimal study run dir (manifest + 1 condition results) for plotting."""
    out_dir = tmp_path / "study_run"
    out_dir.mkdir(parents=True)
    (out_dir / "manifest.json").write_text(
        '{"condition_ids": ["cond_0"], "task": "throughput_sla", "episodes": 1}',
        encoding="utf-8",
    )
    (out_dir / "results" / "cond_0").mkdir(parents=True)
    (out_dir / "results" / "cond_0" / "results.json").write_text(
        '{"task": "throughput_sla", "num_episodes": 1, "base_seed": 42, "seeds": [42], '
        '"episodes": [{"seed": 42, "metrics": {"throughput": 2, '
        '"p95_turnaround_s": 100.0, "violations_by_invariant_id": {}, '
        '"blocked_by_reason_code": {}, "critical_communication_compliance_rate": 1.0, '
        '"tokens_minted": 0, "tokens_consumed": 0}}]}',
        encoding="utf-8",
    )
    return out_dir


def _read_csv_content(path: Path) -> str:
    """Read CSV and return raw content for deterministic comparison."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def test_plots_data_tables_determinism() -> None:
    """Run make_plots twice on same study run; CSV data tables must be identical."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _minimal_study_run(Path(tmp))
        make_plots(out_dir)
        table_paths = get_data_table_paths(out_dir)
        contents1 = {p.name: _read_csv_content(p) for p in table_paths if p.exists()}

        make_plots(out_dir)
        contents2 = {p.name: _read_csv_content(p) for p in table_paths if p.exists()}

        assert set(contents1.keys()) == set(contents2.keys())
        for name in contents1:
            assert contents1[name] == contents2[name], f"Data table {name} must be identical across runs (determinism)"


def test_plots_output_structure() -> None:
    """After make_plots, figures/ and figures/data_tables/ contain expected files."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _minimal_study_run(Path(tmp))
        fig_dir = make_plots(out_dir)

        assert (out_dir / "figures").exists()
        assert (out_dir / "figures" / "data_tables").exists()
        for csv_name in [
            "throughput_vs_violations.csv",
            "trust_cost_vs_p95_tat.csv",
            "violations_by_invariant_id.csv",
            "blocked_by_reason_code_top10.csv",
            "critical_compliance_by_condition.csv",
        ]:
            assert (out_dir / "figures" / "data_tables" / csv_name).exists()

        for base in [
            "throughput_vs_violations",
            "trust_cost_vs_p95_tat",
            "violations_by_invariant_id",
            "blocked_by_reason_code_top10",
            "critical_compliance_by_condition",
        ]:
            assert (fig_dir / f"{base}.png").exists()
            assert (fig_dir / f"{base}.svg").exists()


def test_plots_tables_content_snapshot() -> None:
    """Data tables have expected columns and deterministic content for minimal run."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _minimal_study_run(Path(tmp))
        make_plots(out_dir)

        throughput_csv = out_dir / "figures" / "data_tables" / "throughput_vs_violations.csv"
        assert throughput_csv.exists()
        with throughput_csv.open("r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) >= 1
        assert rows[0] == [
            "condition_id",
            "throughput_mean",
            "throughput_std",
            "throughput_se",
            "violations_total",
        ]
        assert len(rows) == 2  # header + cond_0
        assert rows[1][0] == "cond_0"
        assert float(rows[1][1]) == 2.0  # throughput_mean
        assert int(rows[1][4]) == 0  # violations_total


def test_plots_partial_results_skips_missing_conditions() -> None:
    """When some conditions have no results.json, only conditions with results are plotted.
    Ensures no wrong pairing (cond_id <-> results) and no dropped/zero data for valid conditions.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "partial_run"
        out_dir.mkdir(parents=True)
        (out_dir / "manifest.json").write_text(
            json.dumps({
                "condition_ids": ["cond_0", "cond_1", "cond_2"],
                "condition_labels": ["baseline", "ablation_1", "ablation_2"],
                "task": "throughput_sla",
                "episodes": 1,
            }),
            encoding="utf-8",
        )
        # cond_0: throughput 2, violations 0
        (out_dir / "results" / "cond_0").mkdir(parents=True)
        (out_dir / "results" / "cond_0" / "results.json").write_text(
            json.dumps({
                "task": "throughput_sla",
                "num_episodes": 1,
                "base_seed": 42,
                "seeds": [42],
                "episodes": [{
                    "seed": 42,
                    "metrics": {
                        "throughput": 2,
                        "p95_turnaround_s": 100.0,
                        "violations_by_invariant_id": {},
                        "blocked_by_reason_code": {},
                        "critical_communication_compliance_rate": 1.0,
                        "tokens_minted": 0,
                        "tokens_consumed": 0,
                    },
                }],
            }),
            encoding="utf-8",
        )
        # cond_1: no results.json (missing)
        (out_dir / "results" / "cond_1").mkdir(parents=True)
        # cond_2: throughput 10, violations 1
        (out_dir / "results" / "cond_2").mkdir(parents=True)
        (out_dir / "results" / "cond_2" / "results.json").write_text(
            json.dumps({
                "task": "throughput_sla",
                "num_episodes": 1,
                "base_seed": 44,
                "seeds": [44],
                "episodes": [{
                    "seed": 44,
                    "metrics": {
                        "throughput": 10,
                        "p95_turnaround_s": 50.0,
                        "violations_by_invariant_id": {"inv_x": 1},
                        "blocked_by_reason_code": {},
                        "critical_communication_compliance_rate": 0.9,
                        "tokens_minted": 0,
                        "tokens_consumed": 0,
                    },
                }],
            }),
            encoding="utf-8",
        )
        make_plots(out_dir)
        throughput_csv = out_dir / "figures" / "data_tables" / "throughput_vs_violations.csv"
        assert throughput_csv.exists()
        with throughput_csv.open("r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows[0][0] == "condition_id"
        assert "throughput_mean" in rows[0]
        assert "violations_total" in rows[0]
        assert len(rows) == 3  # header + cond_0 + cond_2 (cond_1 skipped)
        # throughput_mean at index 1, violations_total at index 4
        viol_idx = rows[0].index("violations_total")
        thr_idx = rows[0].index("throughput_mean")
        data_rows = {r[0]: (float(r[thr_idx]), int(r[viol_idx])) for r in rows[1:]}
        assert set(data_rows.keys()) == {"cond_0", "cond_2"}
        assert data_rows["cond_0"] == (2.0, 0)
        assert data_rows["cond_2"] == (10.0, 1)


def test_plots_colorblind_theme() -> None:
    """make_plots with theme=colorblind runs and produces the same set of files."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _minimal_study_run(Path(tmp))
        make_plots(out_dir, theme="colorblind")
        assert (out_dir / "figures" / "throughput_vs_violations.png").exists()
        assert (out_dir / "figures" / "data_tables" / "summary.csv").exists()


def test_plots_pdf_export() -> None:
    """make_plots with pdf=True produces run_figures.pdf."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _minimal_study_run(Path(tmp))
        make_plots(out_dir, pdf=True)
        pdf_path = out_dir / "figures" / "run_figures.pdf"
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
