"""
Tests for coordination_graphs: chart generation for UI bundle.

Ensures graphs are only built when data exists, and that the primary chart
is fully annotated (title, axis labels, footnote).
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.export.coordination_graphs import (
    build_coordination_graphs,
    build_primary_graph_html,
)


def test_build_coordination_graphs_returns_empty_when_no_csv(tmp_path: Path) -> None:
    """No pack_summary or summary_coord under run_dir -> no graphs (cannot be empty)."""
    (tmp_path / "baselines").mkdir(parents=True)
    (tmp_path / "SECURITY").mkdir()
    out = build_coordination_graphs(tmp_path)
    assert out == [], "Must not emit graphs when no summary CSV is present"


def test_build_coordination_graphs_returns_empty_when_csv_has_no_method_id(
    tmp_path: Path,
) -> None:
    """CSV without method_id column or with no valid rows -> no graphs."""
    (tmp_path / "baselines").mkdir(parents=True)
    (tmp_path / "SECURITY").mkdir()
    (tmp_path / "pack_summary.csv").write_text(
        "scale_id,injection_id\nsmall_smoke,none\n",
        encoding="utf-8",
    )
    out = build_coordination_graphs(tmp_path)
    assert out == [], "Must not emit graphs when CSV has no method_id / no leaderboard rows"


def test_primary_graph_has_title_axes_footnote_and_explanation() -> None:
    """Primary SOTA chart must be annotated: title, axes, footnote, and results explanation."""
    leaderboard = [
        {
            "method_id": "kernel_auction_whca_shielded",
            "throughput_mean": 2.0,
            "violations_mean": 50.0,
            "resilience_score_mean": 0.7,
            "attack_success_rate_mean": 0.0,
            "n_cells": 3,
        },
        {
            "method_id": "llm_repair",
            "throughput_mean": 1.0,
            "violations_mean": 100.0,
            "resilience_score_mean": 0.5,
            "attack_success_rate_mean": 0.1,
            "n_cells": 3,
        },
    ]
    html = build_primary_graph_html(leaderboard)
    assert "SOTA key metrics" in html
    assert "Coordination method" in html, "Y-axis (category) must be titled"
    assert "normalized" in html or "Score" in html, "X-axis (value) must be titled"
    assert "chart-footnote" in html and "Source:" in html
    assert "method(s)" in html or "cell(s)" in html
    assert "new Chart(" in html
    assert "chart-explanation" in html, "Results explanation block must be present"
    assert "Results:" in html and "longer bar means a better" in html
