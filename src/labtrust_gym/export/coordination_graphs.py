"""
Coordination metrics graphs for the UI bundle.

Builds self-contained HTML charts (Chart.js via CDN) from pack_summary or
summary_coord data: one primary "key metrics" chart and additional
single-metric and method-class charts. Used by ui-export when coordination
artifacts are present.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.studies.coordination_summarizer import (
    build_method_class_comparison,
    build_sota_leaderboard,
    load_summary_rows,
)


def _find_summary_csv(run_dir: Path) -> Path | None:
    """Return pack_summary.csv or summary_coord path under run_dir or run_dir/coordination_pack."""
    for base in (run_dir, run_dir / "coordination_pack"):
        if not base.is_dir():
            continue
        for sub in ("pack_summary.csv", "summary/summary_coord.csv", "summary_coord.csv"):
            p = base / sub
            if p.is_file():
                return p
    return None


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _normalize_0_1(val: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (val - lo) / (hi - lo)))


def _build_primary_chart_data(leaderboard: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build dataset for primary "key metrics" chart.
    Four metrics, normalized so higher = better for visual comparison:
    - Throughput (norm by max)
    - Resilience (0-1 as-is)
    - Violations: invert (1 - norm) so lower violations = higher bar
    - Attack success: invert (1 - value) so lower attack = higher bar
    """
    methods = [r.get("method_id") or "?" for r in leaderboard]
    tp = [_safe_float(r.get("throughput_mean")) for r in leaderboard]
    res = [_safe_float(r.get("resilience_score_mean")) for r in leaderboard]
    viol = [_safe_float(r.get("violations_mean")) for r in leaderboard]
    attack = [_safe_float(r.get("attack_success_rate_mean")) for r in leaderboard]

    tp_max = max(tp) if tp else 1.0
    viol_max = max(viol) if viol else 1.0

    tp_norm = [t / tp_max if tp_max else 0 for t in tp]
    res_norm = list(res)
    viol_norm = [1.0 - (v / viol_max if viol_max else 0) for v in viol]
    attack_norm = [1.0 - a for a in attack]

    return {
        "labels": methods,
        "datasets": [
            {"label": "Throughput (norm)", "data": tp_norm, "backgroundColor": "rgba(54, 162, 235, 0.7)"},
            {"label": "Resilience", "data": res_norm, "backgroundColor": "rgba(75, 192, 192, 0.7)"},
            {"label": "Safety (1 - violations norm)", "data": viol_norm, "backgroundColor": "rgba(255, 159, 64, 0.7)"},
            {"label": "Security (1 - attack rate)", "data": attack_norm, "backgroundColor": "rgba(153, 102, 255, 0.7)"},
        ],
    }


def _html_wrapper(
    title: str,
    chart_id: str,
    chart_config: dict[str, Any],
    *,
    footnote: str | None = None,
    explanation: str | None = None,
) -> str:
    """Return self-contained HTML with Chart.js (CDN), one chart, optional explanation, and optional footnote."""
    config_json = json.dumps(chart_config)
    explanation_block = ""
    if explanation:
        explanation_block = (
            f'  <p class="chart-explanation" aria-label="How to read the results">'
            f"{explanation}</p>\n"
        )
    footnote_block = ""
    if footnote:
        footnote_block = f'  <p class="chart-footnote" aria-label="Chart annotation">{footnote}</p>\n'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1rem; background: #fafafa; color: #1a1a1a; }}
    .chart-wrapper {{ max-width: 960px; }}
    .chart-container {{ position: relative; width: 100%; height: 420px; margin: 0.5rem 0; }}
    .chart-explanation {{ font-size: 0.9rem; color: #333; margin-top: 0.5rem; line-height: 1.5; max-width: 56rem; }}
    .chart-footnote {{ font-size: 0.85rem; color: #555; margin-top: 0.75rem; line-height: 1.4; }}
  </style>
</head>
<body>
  <div class="chart-wrapper">
    <div class="chart-container">
      <canvas id="{chart_id}" aria-label="{title}"></canvas>
    </div>
{explanation_block}{footnote_block}  </div>
  <script>
    (function() {{
      var config = {config_json};
      var ctx = document.getElementById("{chart_id}").getContext("2d");
      new Chart(ctx, config);
    }})();
  </script>
</body>
</html>
"""


def _make_horizontal_bar_config(
    title: str,
    labels: list[str],
    datasets: list[dict[str, Any]],
    value_label: str = "Value",
    category_axis_label: str = "Coordination method",
    subtitle: str | None = None,
    x_max: float | None = None,
) -> dict[str, Any]:
    """Chart.js config for horizontal bar chart with title, both axes titled, optional subtitle."""
    plugins: dict[str, Any] = {
        "legend": {"display": len(datasets) > 1},
        "title": {
            "display": True,
            "text": title,
            "font": {"size": 16, "weight": "bold"},
            "padding": {"top": 8, "bottom": 12},
        },
    }
    if subtitle:
        plugins["subtitle"] = {
            "display": True,
            "text": subtitle,
            "font": {"size": 12, "weight": "normal"},
            "color": "#555",
            "padding": {"bottom": 16},
        }
    x_scale: dict[str, Any] = {
        "title": {"display": True, "text": value_label, "font": {"size": 12}},
        "min": 0,
        "ticks": {"font": {"size": 11}},
    }
    if x_max is not None:
        x_scale["max"] = x_max
    return {
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "indexAxis": "y",
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": plugins,
            "scales": {
                "x": x_scale,
                "y": {
                    "title": {"display": True, "text": category_axis_label, "font": {"size": 12}},
                    "ticks": {"maxRotation": 0, "autoSkip": False, "font": {"size": 11}},
                },
            },
        },
    }


def build_primary_graph_html(leaderboard: list[dict[str, Any]]) -> str:
    """Build the single state-of-the-art key-metrics chart (grouped horizontal bar)."""
    data = _build_primary_chart_data(leaderboard)
    config = _make_horizontal_bar_config(
        "SOTA key metrics by coordination method",
        data["labels"],
        data["datasets"],
        value_label="Score (normalized; higher is better)",
        category_axis_label="Coordination method",
        subtitle=(
            "Throughput (norm), Resilience (0–1), Safety (1 − violations norm), "
            "Security (1 − attack success rate). All series: higher bar = better."
        ),
        x_max=1.0,
    )
    n_methods = len(leaderboard)
    n_cells = sum((r.get("n_cells") or 0) for r in leaderboard)
    explanation = (
        "Results: Each row is one coordination method; each bar group shows four normalized "
        "metrics (Throughput, Resilience, Safety, Security). Throughput is divided by the "
        "maximum across methods (best = 1). Safety is 1 − (violations / max violations); "
        "Security is 1 − attack_success_rate, so in all four series a longer bar means a better "
        "outcome. Values are means over all cells (scale × injection × phase) for that method. "
        "Use this chart to compare methods at a glance; see the per-metric charts for raw values."
    )
    footnote = (
        f"Source: pack_summary or summary_coord. {n_methods} method(s), {n_cells} cell(s) total. "
        "Safety and Security are inverted so that higher bars indicate better outcomes."
    )
    return _html_wrapper(
        "SOTA key metrics",
        "keyMetricsChart",
        config,
        footnote=footnote,
        explanation=explanation,
    )


def build_throughput_graph_html(leaderboard: list[dict[str, Any]]) -> str:
    """Throughput mean by method."""
    labels = [r.get("method_id") or "?" for r in leaderboard]
    values = [_safe_float(r.get("throughput_mean")) for r in leaderboard]
    datasets = [{"label": "Throughput (mean)", "data": values, "backgroundColor": "rgba(54, 162, 235, 0.7)"}]
    config = _make_horizontal_bar_config(
        "Throughput by coordination method",
        labels,
        datasets,
        value_label="Throughput (specimens released per episode; mean)",
        category_axis_label="Coordination method",
    )
    explanation = (
        "Results: Each bar is the mean number of specimens released (RELEASE_RESULT) per episode "
        "for that coordination method, averaged over all cells (scale × injection × phase). "
        "Higher values indicate more completed work."
    )
    footnote = (
        "Source: pack_summary or summary_coord. Throughput = RELEASE_RESULT count per episode, averaged over cells."
    )
    return _html_wrapper(
        "Throughput by method",
        "throughputChart",
        config,
        footnote=footnote,
        explanation=explanation,
    )


def build_violations_graph_html(leaderboard: list[dict[str, Any]]) -> str:
    """Violations mean by method (lower is better)."""
    labels = [r.get("method_id") or "?" for r in leaderboard]
    values = [_safe_float(r.get("violations_mean")) for r in leaderboard]
    datasets = [{"label": "Violations (mean)", "data": values, "backgroundColor": "rgba(255, 99, 132, 0.7)"}]
    config = _make_horizontal_bar_config(
        "Invariant violations by coordination method",
        labels,
        datasets,
        value_label="Violations (mean count per cell; lower is better)",
        category_axis_label="Coordination method",
        subtitle="Lower bar = fewer safety invariant violations.",
    )
    explanation = (
        "Results: Each bar is the mean count of invariant violations (safety breaches) per cell "
        "for that coordination method. Lower is better; target is zero."
    )
    footnote = "Source: pack_summary or summary_coord. Violations = invariant breaches (safety); target is zero."
    return _html_wrapper(
        "Violations by method",
        "violationsChart",
        config,
        footnote=footnote,
        explanation=explanation,
    )


def build_resilience_graph_html(leaderboard: list[dict[str, Any]]) -> str:
    """Resilience score mean by method."""
    labels = [r.get("method_id") or "?" for r in leaderboard]
    values = [_safe_float(r.get("resilience_score_mean")) for r in leaderboard]
    datasets = [{"label": "Resilience (mean)", "data": values, "backgroundColor": "rgba(75, 192, 192, 0.7)"}]
    config = _make_horizontal_bar_config(
        "Resilience score by coordination method",
        labels,
        datasets,
        value_label="Resilience score (0–1; higher is better)",
        category_axis_label="Coordination method",
        subtitle="Composite of performance, safety, security, and coordination; higher = more resilient.",
    )
    explanation = (
        "Results: Each bar is the mean resilience score (0–1) for that coordination method, "
        "averaged over all cells. Resilience combines performance, safety, security, and "
        "coordination; higher is better."
    )
    footnote = "Source: pack_summary or summary_coord. Resilience = composite metric over cells; 1 = best."
    return _html_wrapper(
        "Resilience by method",
        "resilienceChart",
        config,
        footnote=footnote,
        explanation=explanation,
    )


def build_method_class_graph_html(method_class_rows: list[dict[str, Any]]) -> str:
    """Throughput and resilience by method class (horizontal bar, two series)."""
    labels = [r.get("method_class") or "?" for r in method_class_rows]
    tp = [_safe_float(r.get("throughput_mean")) for r in method_class_rows]
    res = [_safe_float(r.get("resilience_score_mean")) for r in method_class_rows]
    datasets = [
        {"label": "Throughput (mean)", "data": tp, "backgroundColor": "rgba(54, 162, 235, 0.7)"},
        {"label": "Resilience (mean)", "data": res, "backgroundColor": "rgba(75, 192, 192, 0.7)"},
    ]
    config = _make_horizontal_bar_config(
        "Method class comparison: throughput and resilience",
        labels,
        datasets,
        value_label="Mean value (throughput or resilience 0–1)",
        category_axis_label="Method class",
        subtitle="Aggregated by coordination class (e.g. kernel_schedulers, llm, centralized).",
    )
    explanation = (
        "Results: Each row is a method class (e.g. kernel_schedulers, llm, centralized). "
        "Bars show mean throughput (specimens per episode) and mean resilience (0–1) aggregated "
        "across all methods in that class. Use to compare families of coordination strategies."
    )
    footnote = "Source: pack_summary or summary_coord. Classes from method_id mapping (kernel_*, llm_*, etc.)."
    return _html_wrapper(
        "Method class comparison",
        "methodClassChart",
        config,
        footnote=footnote,
        explanation=explanation,
    )


def build_coordination_graphs(run_dir: Path) -> list[tuple[str, str]]:
    """
    Build all coordination graphs from pack_summary (or summary_coord) under run_dir.

    Returns list of (relative_path, html_content) for inclusion in the UI bundle.
    relative_path is under coordination/ (e.g. graphs/sota_key_metrics.html).
    """
    csv_path = _find_summary_csv(run_dir)
    if not csv_path or not csv_path.is_file():
        return []

    try:
        rows = load_summary_rows(csv_path)
    except Exception:
        return []

    if not rows:
        return []

    leaderboard = build_sota_leaderboard(rows)
    if not leaderboard:
        return []

    method_class = build_method_class_comparison(rows, None)
    out: list[tuple[str, str]] = []

    # Paths relative to coordination/ in the zip (e.g. graphs/sota_key_metrics.html).
    primary_html = build_primary_graph_html(leaderboard)
    out.append(("graphs/sota_key_metrics.html", primary_html))

    throughput_html = build_throughput_graph_html(leaderboard)
    out.append(("graphs/throughput_by_method.html", throughput_html))

    violations_html = build_violations_graph_html(leaderboard)
    out.append(("graphs/violations_by_method.html", violations_html))

    resilience_html = build_resilience_graph_html(leaderboard)
    out.append(("graphs/resilience_by_method.html", resilience_html))

    if method_class:
        method_class_html = build_method_class_graph_html(method_class)
        out.append(("graphs/method_class_comparison.html", method_class_html))

    return out


# Labels for UI bundle index (coordination_artifacts).
GRAPH_ARTIFACT_LABELS: dict[str, str] = {
    "graphs/sota_key_metrics.html": "SOTA key metrics (chart)",
    "graphs/throughput_by_method.html": "Throughput by method (chart)",
    "graphs/violations_by_method.html": "Violations by method (chart)",
    "graphs/resilience_by_method.html": "Resilience by method (chart)",
    "graphs/method_class_comparison.html": "Method class comparison (chart)",
}
