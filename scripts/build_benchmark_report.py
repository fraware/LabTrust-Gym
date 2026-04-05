#!/usr/bin/env python3
"""
Build a presentable HTML (and JSON snapshot) benchmark report from existing
run artifacts: method_status.jsonl (latest method_end per method) plus optional
enrichment from per-cell results.json under the run directory.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.coordination.registry import BUILTIN_COORDINATION_METHOD_IDS
from labtrust_gym.benchmarks.presentation.pipeline import (
    BENCHMARK_BUNDLE_SCHEMA_VERSION,
    build_presentation_manifest,
    compute_run_analytics,
    default_report_out_dir,
    first_git_sha_from_rows,
    load_run_meta,
    load_run_summary,
    write_methods_matrix_csv,
)

# Subresource Integrity for Chart.js 4.4.1 (jsDelivr UMD); pin version for supply-chain stability.
_CHARTJS_441_INTEGRITY = (
    "sha384-9nhczxUqK87bcKHh20fSQcTGD4qq5GhayNYSYWqwBkINBhOfQLg/P5HG5lF1urn4"
)


def _parse_iso(ts: str | None) -> str:
    if not ts:
        return ""
    return str(ts)


def _latest_method_ends(status_path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not status_path.is_file():
        return latest
    for line in status_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") != "method_end":
            continue
        method = row.get("method")
        if not method:
            continue
        ended = _parse_iso(row.get("ended_at"))
        prev = latest.get(method)
        if prev is None or ended > _parse_iso(prev.get("ended_at")):
            latest[method] = row
    return latest


def _cell_results_path(run_dir: Path, scale_id: str, method: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_\-]+", "_", method)
    return run_dir / f"{scale_id}_{safe}_none" / "results.json"


def _resolve_results_path(
    run_dir: Path,
    scale_id: str,
    method: str,
    logged_result_path: str | None,
) -> Path:
    """Resolve results.json for report enrichment.

    Use *logged_result_path* only when that file exists. Otherwise use the
    canonical ``{scale_id}_{method}_none/results.json`` under *run_dir*.

    Logged paths are often absolute Linux paths from the machine that ran the
    benchmark; after copying the run tree to another host, they are stale.
    """
    if logged_result_path:
        candidate = Path(logged_result_path)
        if candidate.is_file():
            return candidate
    return _cell_results_path(run_dir, scale_id, method)


def _enrich_results(results_path: Path) -> dict[str, Any] | None:
    if not results_path.is_file():
        return None
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    eps = data.get("episodes") or []
    throughputs: list[float] = []
    steps_list: list[int] = []
    resilience: list[float] = []
    transport_total = 0
    for ep in eps:
        if not isinstance(ep, dict):
            continue
        m = ep.get("metrics") or {}
        if isinstance(m, dict):
            th = m.get("throughput")
            if isinstance(th, (int, float)):
                throughputs.append(float(th))
            st = m.get("steps")
            if isinstance(st, int):
                steps_list.append(st)
            rob = m.get("robustness") or {}
            if isinstance(rob, dict):
                rs = rob.get("resilience_score")
                if isinstance(rs, (int, float)):
                    resilience.append(float(rs))
            tc = m.get("transport_consignment_count")
            if isinstance(tc, int):
                transport_total += tc
    return {
        "llm_model_id": data.get("llm_model_id"),
        "pipeline_mode": data.get("pipeline_mode"),
        "llm_backend_id": data.get("llm_backend_id"),
        "num_episodes": data.get("num_episodes"),
        "git_sha": (data.get("git_sha") or data.get("git_commit_hash"))[:12]
        if (data.get("git_sha") or data.get("git_commit_hash"))
        else None,
        "mean_throughput": sum(throughputs) / len(throughputs) if throughputs else None,
        "mean_steps": sum(steps_list) / len(steps_list) if steps_list else None,
        "max_steps": (data.get("config") or {}).get("max_steps"),
        "mean_resilience": sum(resilience) / len(resilience) if resilience else None,
        "total_transport_consignment": transport_total,
    }


def _duration_seconds(started_at: Any, ended_at: Any) -> float | None:
    if not started_at or not ended_at:
        return None
    try:
        s = str(started_at).replace("Z", "+00:00")
        e = str(ended_at).replace("Z", "+00:00")
        t0 = datetime.fromisoformat(s)
        t1 = datetime.fromisoformat(e)
        sec = (t1 - t0).total_seconds()
        return float(sec) if sec >= 0 else None
    except (TypeError, ValueError):
        return None


def _bar_colors_for_rows(rows: list[dict[str, Any]]) -> list[str]:
    colors: list[str] = []
    for r in rows:
        st = r["status"]
        if st == "PENDING":
            colors.append("rgba(148, 163, 184, 0.35)")
        elif st == "FAIL":
            colors.append("rgba(251, 113, 133, 0.78)")
        elif st == "ARTIFACT":
            colors.append("rgba(196, 181, 253, 0.78)")
        elif r.get("family") == "llm":
            colors.append("rgba(212, 165, 116, 0.92)")
        else:
            colors.append("rgba(129, 140, 248, 0.88)")
    return colors


def _chart_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [r["method"] for r in rows]
    colors = _bar_colors_for_rows(rows)
    duration_h: list[float | None] = []
    for r in rows:
        ds = r.get("duration_s")
        if isinstance(ds, (int, float)) and ds >= 0:
            duration_h.append(round(float(ds) / 3600.0, 4))
        else:
            duration_h.append(None)
    llm_calls = [int(r["llm_calls"]) if r.get("llm_calls") is not None else 0 for r in rows]
    meta_tok = [
        int(r["metadata_total_tokens"]) if r.get("metadata_total_tokens") is not None else 0
        for r in rows
    ]
    mean_tp: list[float | None] = []
    mean_rs: list[float | None] = []
    transport: list[int] = []
    for r in rows:
        en = r.get("enrich") or {}
        v = en.get("mean_throughput")
        mean_tp.append(float(v) if isinstance(v, (int, float)) else None)
        w = en.get("mean_resilience")
        mean_rs.append(float(w) if isinstance(w, (int, float)) else None)
        tc = en.get("total_transport_consignment")
        transport.append(int(tc) if isinstance(tc, int) else 0)
    return {
        "labels": labels,
        "colors": colors,
        "durationHours": duration_h,
        "llmCalls": llm_calls,
        "metaTokens": meta_tok,
        "meanThroughput": mean_tp,
        "meanResilience": mean_rs,
        "transportTotal": transport,
        "statuses": [r["status"] for r in rows],
    }


def _render_charts_block(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(_chart_payload(rows))
    chart_script_tag = (
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" '
        f'integrity="{_CHARTJS_441_INTEGRITY}" crossorigin="anonymous"></script>'
    )
    return (
        """
    <section id="charts" class="charts-wrap">
      <h2 class="section-title">Comparison charts</h2>
      <p class="section-lead">Same method order as the catalog in all charts
        (classical = indigo, LLM = sand, pending = gray). Wall time is from
        <span class="mono">method_status.jsonl</span> start/end. Resilience and
        throughput are means over episodes in each cell&rsquo;s
        <span class="mono">results.json</span>.</p>
      <div class="chart-legend">
        <span><i class="swatch" style="background:rgba(129,140,248,0.88)"></i> Classical</span>
        <span><i class="swatch" style="background:rgba(212,165,116,0.92)"></i> LLM</span>
        <span><i class="swatch" style="background:rgba(148,163,184,0.35)"></i> Pending</span>
        <span><i class="swatch" style="background:rgba(251,113,133,0.78)"></i> Fail</span>
      </div>
      <div class="charts-grid">
        <div class="chart-card">
          <h3>Wall-clock run time</h3>
          <div class="canvas-box"><canvas id="ltgChartDuration" aria-label="Duration"></canvas></div>
        </div>
        <div class="chart-card">
          <h3>LLM API calls (logged)</h3>
          <div class="canvas-box"><canvas id="ltgChartCalls" aria-label="LLM calls"></canvas></div>
        </div>
        <div class="chart-card">
          <h3>Mean resilience score</h3>
          <div class="canvas-box"><canvas id="ltgChartResilience" aria-label="Resilience"></canvas></div>
        </div>
        <div class="chart-card">
          <h3>Metadata tokens (logged)</h3>
          <div class="canvas-box"><canvas id="ltgChartTokens" aria-label="Tokens"></canvas></div>
        </div>
        <div class="chart-card">
          <h3>Mean throughput (episodes)</h3>
          <div class="canvas-box"><canvas id="ltgChartThroughput" aria-label="Throughput"></canvas></div>
        </div>
        <div class="chart-card">
          <h3>Transport consignments (sum)</h3>
          <div class="canvas-box"><canvas id="ltgChartTransport" aria-label="Transport"></canvas></div>
        </div>
      </div>
    </section>
    <script type="application/json" id="ltg-bench-charts-json">"""
        + payload
        + """</script>
    __CHART_SCRIPT__
    <script>
    (function () {
      var el = document.getElementById("ltg-bench-charts-json");
      if (!el || typeof Chart === "undefined") return;
      var P = JSON.parse(el.textContent);
      var tickColor = "#9a948a";
      var gridColor = "rgba(255,255,255,0.06)";
      var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      function horizBar(canvasId, values, xLabel, barOpts) {
        barOpts = barOpts || {};
        var ctx = document.getElementById(canvasId);
        if (!ctx) return;
        new Chart(ctx, {
          type: "bar",
          data: {
            labels: P.labels,
            datasets: [{
              data: values,
              backgroundColor: P.colors,
              borderWidth: 0,
              borderRadius: 4,
            }],
          },
          options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            animation: reduceMotion ? false : { duration: 450 },
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  label: function (c) {
                    var v = c.parsed.x;
                    if (v === null || typeof v === "undefined") return "n/a";
                    if (barOpts.tooltipFormat) return barOpts.tooltipFormat(v);
                    return String(v);
                  },
                },
              },
            },
            scales: {
              x: {
                title: { display: !!xLabel, text: xLabel || "", color: tickColor },
                ticks: { color: tickColor },
                grid: { color: gridColor },
              },
              y: {
                ticks: { color: "#c8c2b8", font: { size: 9 } },
                grid: { display: false },
              },
            },
          },
        });
      }
      horizBar("ltgChartDuration", P.durationHours, "Hours (wall)", {
        tooltipFormat: function (v) {
          return (Math.round(v * 3600) / 3600).toFixed(3) + " h";
        },
      });
      horizBar("ltgChartCalls", P.llmCalls, "Call count");
      horizBar("ltgChartResilience", P.meanResilience, "0–1 mean", {
        tooltipFormat: function (v) {
          return v.toFixed(4);
        },
      });
      horizBar("ltgChartTokens", P.metaTokens, "Token count");
      horizBar("ltgChartThroughput", P.meanThroughput, "Mean / episode", {
        tooltipFormat: function (v) {
          return v.toFixed(5);
        },
      });
      horizBar("ltgChartTransport", P.transportTotal, "Sum over episodes");
    })();
    </script>
    """
    ).replace("__CHART_SCRIPT__", chart_script_tag)


def _fmt_num(n: Any, *, digits: int = 2) -> str:
    if n is None:
        return "—"
    if isinstance(n, bool):
        return str(n)
    if isinstance(n, int):
        return f"{n:,}"
    try:
        x = float(n)
    except (TypeError, ValueError):
        return "—"
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}"
    return f"{x:,.{digits}f}"


def _fmt_pct(n: Any) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n) * 100:.2f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_duration_wall(s: Any) -> str:
    if s is None:
        return "—"
    try:
        sec = float(s)
        if sec < 60:
            return f"{sec:.0f}s"
        if sec < 3600:
            return f"{sec / 60.0:.1f}m"
        return f"{sec / 3600.0:.2f}h"
    except (TypeError, ValueError):
        return "—"


def _escape(s: Any) -> str:
    return html.escape(str(s) if s is not None else "", quote=True)


def sort_rows_for_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda x: (
            0 if x["status"] == "FAIL" else 1 if x["status"] == "PENDING" else 2,
            x["family"],
            x["method"],
        ),
    )


def _method_row_sort_attrs(r: dict[str, Any]) -> str:
    en = r.get("enrich") or {}
    mdl = r.get("llm_model_id") or en.get("llm_model_id") or ""
    rp = r.get("result_path") or ""
    art = Path(rp).name if rp else ""
    ds = r.get("duration_s")
    eps = en.get("num_episodes")
    tp = en.get("mean_throughput")
    rs = en.get("mean_resilience")
    tc = en.get("total_transport_consignment")
    lc = r.get("llm_calls")
    mt = r.get("metadata_total_tokens")
    er = r.get("llm_error_rate")

    def num_str(v: Any) -> str:
        if isinstance(v, (int, float)):
            return str(float(v))
        return ""

    eps_s = str(int(eps)) if isinstance(eps, int) else ""
    tc_s = str(int(tc)) if isinstance(tc, int) else ""
    lc_s = str(int(lc)) if isinstance(lc, int) else ""
    mt_s = str(int(mt)) if isinstance(mt, int) else ""

    parts = [
        f'data-m="{html.escape(str(r.get("method") or ""), quote=True)}"',
        f'data-fam="{html.escape(str(r.get("family") or ""), quote=True)}"',
        f'data-st="{html.escape(str(r.get("status") or ""), quote=True)}"',
        f'data-ws="{num_str(ds)}"',
        f'data-mdl="{html.escape(str(mdl), quote=True)}"',
        f'data-eps="{eps_s}"',
        f'data-thr="{num_str(tp)}"',
        f'data-rsil="{num_str(rs)}"',
        f'data-tc="{tc_s}"',
        f'data-lc="{lc_s}"',
        f'data-mt="{mt_s}"',
        f'data-er="{num_str(er)}"',
        f'data-end="{html.escape(str(r.get("ended_at") or ""), quote=True)}"',
        f'data-art="{html.escape(art, quote=True)}"',
    ]
    return " ".join(parts)


def _matrix_interaction_script() -> str:
    return """
    <script>
    (function () {
      var tb = document.getElementById("ltg-method-tbody");
      if (!tb) return;
      var filterEl = document.getElementById("ltg-matrix-filter");
      var sortState = { key: null, dir: 1 };

      function attr(tr, k) {
        return tr.getAttribute("data-" + k) || "";
      }

      function cmp(trA, trB, key, type, dir) {
        if (type === "str") {
          var a = attr(trA, key).toLowerCase();
          var b = attr(trB, key).toLowerCase();
          if (a < b) return -dir;
          if (a > b) return dir;
          return 0;
        }
        var sa = attr(trA, key);
        var sb = attr(trB, key);
        if (!sa && !sb) return 0;
        if (!sa) return dir;
        if (!sb) return -dir;
        var na = parseFloat(sa);
        var nb = parseFloat(sb);
        na = isNaN(na) ? -Infinity : na;
        nb = isNaN(nb) ? -Infinity : nb;
        return dir * (na - nb);
      }

      function applySort(key, type) {
        if (sortState.key === key) sortState.dir *= -1;
        else {
          sortState.key = key;
          sortState.dir = 1;
        }
        var dir = sortState.dir;
        var rows = Array.prototype.slice.call(tb.querySelectorAll("tr"));
        rows.sort(function (a, b) {
          return cmp(a, b, key, type, dir);
        });
        rows.forEach(function (r) {
          tb.appendChild(r);
        });
        document.querySelectorAll(".sort-btn").forEach(function (btn) {
          var ind = btn.querySelector(".sort-ind");
          if (!ind) return;
          var active = btn.getAttribute("data-ltg-sort") === key;
          ind.textContent = active ? (dir > 0 ? "\u2193" : "\u2191") : "";
        });
      }

      document.querySelectorAll(".sort-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var k = btn.getAttribute("data-ltg-sort");
          var t = btn.getAttribute("data-ltg-type") || "str";
          if (k) applySort(k, t);
        });
      });

      if (filterEl) {
        filterEl.addEventListener("input", function () {
          var q = filterEl.value.trim().toLowerCase();
          Array.prototype.forEach.call(tb.querySelectorAll("tr"), function (tr) {
            var m = (tr.getAttribute("data-m") || "").toLowerCase();
            tr.style.display = !q || m.indexOf(q) !== -1 ? "" : "none";
          });
        });
      }
    })();
    </script>
    """


def build_rows(
    run_dir: Path,
    scale_id: str,
    catalog: tuple[str, ...],
) -> list[dict[str, Any]]:
    status_path = run_dir / "method_status.jsonl"
    latest = _latest_method_ends(status_path)
    rows: list[dict[str, Any]] = []
    for method in catalog:
        is_llm = method.startswith("llm_")
        end = latest.get(method)
        rpath = end.get("result_path") if end else None
        res_file = _resolve_results_path(run_dir, scale_id, method, rpath)
        enrich = _enrich_results(res_file)
        if end:
            status = str(end.get("status") or "UNKNOWN")
            ended_at = end.get("ended_at")
            started_at = end.get("started_at")
            reason = end.get("reason")
        elif enrich:
            status = "ARTIFACT"
            ended_at = None
            started_at = None
            reason = "results.json on disk; no matching method_end in log"
        else:
            status = "PENDING"
            ended_at = None
            started_at = None
            reason = None

        duration_s = _duration_seconds(started_at, ended_at)

        rows.append(
            {
                "method": method,
                "family": "llm" if is_llm else "classical",
                "status": status,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_s": duration_s,
                "reason": reason,
                "llm_model_id": (end or {}).get("llm_model_id") if end else None,
                "llm_calls": (end or {}).get("llm_calls") if end else None,
                "llm_error_rate": (end or {}).get("llm_error_rate") if end else None,
                "metadata_total_tokens": (end or {}).get("metadata_total_tokens")
                if end
                else None,
                "invalid_output_rate": (end or {}).get("invalid_output_rate")
                if end
                else None,
                "result_path": str(res_file) if res_file.is_file() else None,
                "enrich": enrich,
            }
        )
    return rows


def _nav_html() -> str:
    return """
  <nav class="top-nav mono" aria-label="Report sections">
    <a href="#briefing">Briefing</a><span class="nav-sep">·</span>
    <a href="#kpis">Coverage</a><span class="nav-sep">·</span>
    <a href="#charts">Charts</a><span class="nav-sep">·</span>
    <a href="#matrix-tools">Table &amp; exports</a>
  </nav>"""


def _briefing_html(
    run_meta: dict[str, Any],
    run_summary: dict[str, Any] | None,
    analytics: dict[str, Any],
    run_dir: Path,
    scale_id: str,
) -> str:
    meta_scale = run_meta.get("scale_id") or scale_id
    model = run_meta.get("model")
    eps = run_meta.get("episodes")
    seed = run_meta.get("seed")
    started = run_meta.get("started_at")
    backend = run_meta.get("llm_backend")
    if run_summary:
        sweep = (
            f"Finished sweep: {run_summary.get('pass_count')} pass, "
            f"{run_summary.get('fail_count')} fail of "
            f"{run_summary.get('total_methods')} methods."
        )
    else:
        sweep = (
            "No run_summary.json — sweep incomplete or interrupted before "
            "final write."
        )
    tw = analytics.get("total_wall_clock_hours")
    tw_s = f"{float(tw):,.2f} h" if isinstance(tw, (int, float)) else "—"
    calls = analytics.get("sum_llm_calls")
    calls_s = _fmt_num(calls) if isinstance(calls, int) else "—"
    toks = analytics.get("sum_metadata_tokens")
    toks_s = _fmt_num(toks) if isinstance(toks, int) else "—"
    longest = analytics.get("longest_method_wall") or {}
    lm = longest.get("method")
    ls = longest.get("seconds")
    long_s = "—"
    if isinstance(lm, str) and isinstance(ls, (int, float)):
        long_s = f"{_escape(lm)} ({float(ls) / 3600.0:.2f} h)"
    mr = analytics.get("mean_resilience_over_methods_with_data")
    mr_s = f"{float(mr):.3f}" if isinstance(mr, (int, float)) else "—"
    return f"""
    <section id="briefing" class="briefing">
      <h2 class="briefing-title">Run briefing</h2>
      <div class="briefing-grid">
        <dl class="briefing-dl">
          <dt>Run directory</dt><dd class="mono">{_escape(run_dir.name)}</dd>
          <dt>Scale</dt><dd class="mono">{_escape(str(meta_scale))}</dd>
          <dt>LLM model</dt><dd class="mono">{_escape(str(model or '—'))}</dd>
          <dt>Episodes / seed</dt><dd class="mono">{_escape(str(eps))} / {_escape(str(seed))}</dd>
          <dt>Live backend</dt><dd class="mono">{_escape(str(backend or '—'))}</dd>
          <dt>Run started</dt><dd class="mono">{_escape(str(started or '—'))}</dd>
        </dl>
        <dl class="briefing-dl accent-dl">
          <dt>Σ wall time (completed cells)</dt><dd>{_escape(tw_s)}</dd>
          <dt>Σ LLM calls (logged)</dt><dd>{_escape(calls_s)}</dd>
          <dt>Σ metadata tokens</dt><dd>{_escape(toks_s)}</dd>
          <dt>Mean resilience (methods w/ data)</dt><dd>{_escape(mr_s)}</dd>
          <dt>Longest method (wall)</dt><dd class="small">{long_s}</dd>
          <dt>Sweep</dt><dd class="small">{_escape(sweep)}</dd>
        </dl>
      </div>
    </section>"""


def _insights_html(analytics: dict[str, Any]) -> str:
    ins = analytics.get("insights")
    if not isinstance(ins, list) or not ins:
        return ""
    items = "".join(f"<li>{_escape(str(t))}</li>" for t in ins)
    return f"""
    <section id="insights" class="insights" aria-label="Automated insights">
      <h2 class="insights-title">Analysis highlights</h2>
      <ul class="insights-list">{items}</ul>
    </section>"""


def render_html(
    rows: list[dict[str, Any]],
    *,
    title: str,
    run_dir: Path,
    scale_id: str,
    generated_at: str,
    run_meta: dict[str, Any] | None = None,
    run_summary: dict[str, Any] | None = None,
    analytics: dict[str, Any] | None = None,
) -> str:
    run_meta = run_meta or {}
    analytics = analytics or {}
    charts_html = _render_charts_block(rows)
    nav_html = _nav_html()
    briefing_html = _briefing_html(run_meta, run_summary, analytics, run_dir, scale_id)
    insights_html = _insights_html(analytics)
    pass_n = sum(1 for r in rows if r["status"] == "PASS")
    fail_n = sum(1 for r in rows if r["status"] == "FAIL")
    pending_n = sum(1 for r in rows if r["status"] == "PENDING")
    artifact_n = sum(1 for r in rows if r["status"] == "ARTIFACT")
    total = len(rows)

    def row_html(r: dict[str, Any]) -> str:
        st = r["status"]
        badge_class = {
            "PASS": "badge pass",
            "FAIL": "badge fail",
            "PENDING": "badge pending",
            "ARTIFACT": "badge artifact",
        }.get(st, "badge")
        en = r.get("enrich") or {}
        tp = en.get("mean_throughput")
        rs = en.get("mean_resilience")
        rs_cell = _fmt_num(rs, digits=3) if isinstance(rs, (int, float)) else "—"
        wall = _fmt_duration_wall(r.get("duration_s"))
        mdl = r.get("llm_model_id") or en.get("llm_model_id")
        episodes = en.get("num_episodes")
        short_path = ""
        if r.get("result_path"):
            short_path = Path(r["result_path"]).name

        err = r.get("llm_error_rate")
        err_cell = _fmt_pct(err) if err is not None else "—"
        rp = r.get("result_path") or ""
        reason = r.get("reason")
        badge_title = f' title="{_escape(reason)}"' if reason else ""
        tc = en.get("total_transport_consignment")
        tc_cell = _fmt_num(tc) if isinstance(tc, int) else "—"

        sort_attrs = _method_row_sort_attrs(r)
        return f"""<tr class="row-{st.lower()}" {sort_attrs}>
<td class="mono method-name">{_escape(r["method"])}</td>
<td><span class="family">{_escape(r["family"])}</span></td>
<td><span class="{badge_class}"{badge_title}>{_escape(st)}</span></td>
<td class="num small">{_escape(wall)}</td>
<td class="mono small">{_escape(mdl)}</td>
<td class="num">{_fmt_num(episodes)}</td>
<td class="num">{_fmt_num(tp, digits=3)}</td>
<td class="num">{_escape(rs_cell)}</td>
<td class="num">{_escape(tc_cell)}</td>
<td class="num">{_fmt_num(r.get('llm_calls'))}</td>
<td class="num">{_fmt_num(r.get('metadata_total_tokens'))}</td>
<td class="num">{err_cell}</td>
<td class="small time">{_escape(r.get('ended_at') or '—')}</td>
<td class="mono tiny" title="{_escape(rp)}">{_escape(short_path or '—')}</td>
</tr>"""

    rows_sorted = sort_rows_for_table(rows)
    tbody = "\n".join(row_html(r) for r in rows_sorted)
    matrix_script = _matrix_interaction_script()

    tw = analytics.get("total_wall_clock_hours")
    tw_card = f"{float(tw):,.2f}" if isinstance(tw, (int, float)) else "—"
    sc = analytics.get("sum_llm_calls")
    sc_card = _fmt_num(sc) if isinstance(sc, int) else "—"
    st = analytics.get("sum_metadata_tokens")
    st_card = _fmt_num(st) if isinstance(st, int) else "—"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="description" content="LabTrust Gym coordination sweep report: briefing, comparative charts, sortable method matrix, and exportable CSV/JSON."/>
  <title>{_escape(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Source+Sans+3:ital,wght@0,400;0,600;0,700;1,400&display=swap" rel="stylesheet"/>
  <style>
    :root {{
      --bg: #0f1114;
      --surface: #171a1f;
      --surface2: #1e2329;
      --text: #e8e4dc;
      --muted: #9a948a;
      --accent: #d4a574;
      --accent-dim: #8b6914;
      --pass: #6ee7b7;
      --pass-bg: rgba(110, 231, 183, 0.12);
      --fail: #fb7185;
      --fail-bg: rgba(251, 113, 133, 0.12);
      --pending: #94a3b8;
      --pending-bg: rgba(148, 163, 184, 0.1);
      --artifact: #c4b5fd;
      --artifact-bg: rgba(196, 181, 253, 0.12);
      --border: rgba(212, 165, 116, 0.22);
      --radius: 14px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Source Sans 3", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
      background-image:
        radial-gradient(ellipse 120% 80% at 10% -20%, rgba(212, 165, 116, 0.09), transparent 50%),
        radial-gradient(ellipse 90% 60% at 100% 0%, rgba(99, 102, 241, 0.06), transparent 45%);
    }}
    .wrap {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 2.5rem 1.5rem 4rem;
    }}
    header {{
      margin-bottom: 2.75rem;
      padding-bottom: 2rem;
      border-bottom: 1px solid var(--border);
    }}
    h1 {{
      font-family: Fraunces, Georgia, serif;
      font-weight: 700;
      font-size: clamp(2rem, 4vw, 2.75rem);
      letter-spacing: -0.02em;
      margin: 0 0 0.5rem;
      color: var(--text);
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 1.05rem;
      max-width: 52ch;
    }}
    .meta {{
      margin-top: 1.25rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem 1.5rem;
      font-size: 0.875rem;
      color: var(--muted);
    }}
    .meta strong {{ color: var(--accent); font-weight: 600; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 1rem;
      margin-bottom: 2.5rem;
    }}
    .card {{
      background: linear-gradient(165deg, var(--surface) 0%, var(--surface2) 100%);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.15rem 1.25rem;
      position: relative;
      overflow: hidden;
    }}
    .card::after {{
      content: "";
      position: absolute;
      top: 0; right: 0;
      width: 48%; height: 100%;
      background: linear-gradient(105deg, transparent, rgba(212, 165, 116, 0.04));
      pointer-events: none;
    }}
    .card .label {{
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
      margin-bottom: 0.35rem;
    }}
    .card .value {{
      font-family: Fraunces, Georgia, serif;
      font-size: 1.85rem;
      font-weight: 600;
    }}
    .card.pass .value {{ color: var(--pass); }}
    .card.fail .value {{ color: var(--fail); }}
    .card.pending .value {{ color: var(--pending); }}
    .card.total .value {{ color: var(--accent); }}
    .top-nav {{
      position: sticky;
      top: 0;
      z-index: 40;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem 0.75rem;
      padding: 0.65rem 0;
      margin: 0 0 1.75rem;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(15,17,20,0.94), rgba(15,17,20,0.88));
      backdrop-filter: blur(14px);
      font-size: 0.8rem;
    }}
    .top-nav a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
    .top-nav a:hover {{ text-decoration: underline; }}
    .nav-sep {{ color: var(--muted); user-select: none; }}
    .briefing {{
      margin-bottom: 2rem;
      padding: 1.35rem 1.5rem;
      background: linear-gradient(145deg, var(--surface) 0%, rgba(30,35,45,0.95) 100%);
      border: 1px solid var(--border);
      border-radius: calc(var(--radius) + 4px);
      box-shadow: 0 16px 40px rgba(0,0,0,0.3);
    }}
    .briefing-title {{
      font-family: Fraunces, Georgia, serif;
      font-size: 1.2rem;
      font-weight: 600;
      margin: 0 0 1rem;
      color: var(--text);
    }}
    .briefing-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 1.5rem 2rem;
    }}
    .briefing-dl {{
      margin: 0;
      display: grid;
      gap: 0.5rem 0.75rem;
    }}
    .briefing-dl dt {{
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
      margin: 0;
    }}
    .briefing-dl dd {{
      margin: 0;
      font-size: 0.9rem;
      color: var(--text);
    }}
    .accent-dl dt {{ color: var(--accent-dim); }}
    .insights {{
      margin-bottom: 2rem;
      padding: 1.1rem 1.35rem;
      border-left: 4px solid var(--accent);
      background: rgba(212, 165, 116, 0.08);
      border-radius: 0 var(--radius) var(--radius) 0;
    }}
    .insights-title {{
      font-family: Fraunces, Georgia, serif;
      font-size: 1.05rem;
      margin: 0 0 0.65rem;
      color: var(--accent);
    }}
    .insights-list {{
      margin: 0;
      padding-left: 1.2rem;
      color: var(--text);
      font-size: 0.9rem;
    }}
    .insights-list li {{ margin-bottom: 0.4rem; }}
    .kpi-deep .card .value {{ font-size: 1.45rem; }}
    @media print {{
      .top-nav {{ display: none; }}
      body {{ background: #fff; color: #111; }}
      .wrap {{ max-width: 100%; }}
      .chart-card .canvas-box {{ height: 480px; }}
    }}
    .charts-wrap {{
      margin-bottom: 2.5rem;
    }}
    .charts-wrap .section-title {{
      font-family: Fraunces, Georgia, serif;
      font-size: 1.35rem;
      font-weight: 600;
      margin: 0 0 1rem;
      color: var(--text);
    }}
    .charts-wrap .section-lead {{
      color: var(--muted);
      font-size: 0.9rem;
      max-width: 70ch;
      margin: 0 0 1.5rem;
      line-height: 1.5;
    }}
    .charts-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 520px), 1fr));
      gap: 1.25rem;
    }}
    .chart-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: calc(var(--radius) + 2px);
      padding: 1rem 1rem 0.5rem;
      box-shadow: 0 12px 32px rgba(0,0,0,0.28);
    }}
    .chart-card h3 {{
      font-family: Fraunces, Georgia, serif;
      font-size: 0.95rem;
      font-weight: 600;
      margin: 0 0 0.75rem;
      color: var(--accent);
    }}
    .chart-card .canvas-box {{
      position: relative;
      height: min(920px, 110vh);
      width: 100%;
    }}
    .chart-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem 1.25rem;
      margin: 0.5rem 0 1.25rem;
      font-size: 0.75rem;
      color: var(--muted);
    }}
    .chart-legend span {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }}
    .swatch {{
      width: 10px;
      height: 10px;
      border-radius: 2px;
      display: inline-block;
    }}
    section.table-section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: calc(var(--radius) + 4px);
      overflow: hidden;
      box-shadow: 0 24px 48px rgba(0,0,0,0.35);
    }}
    .table-head {{
      padding: 1.1rem 1.35rem;
      background: linear-gradient(180deg, var(--surface2), var(--surface));
      border-bottom: 1px solid var(--border);
    }}
    .table-head h2 {{
      font-family: Fraunces, Georgia, serif;
      font-size: 1.25rem;
      margin: 0;
      font-weight: 600;
    }}
    .table-head p {{
      margin: 0.35rem 0 0;
      font-size: 0.85rem;
      color: var(--muted);
    }}
    .table-scroll {{
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }}
    th {{
      text-align: left;
      padding: 0.75rem 1rem;
      background: rgba(0,0,0,0.25);
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-size: 0.68rem;
      white-space: nowrap;
      border-bottom: 1px solid var(--border);
    }}
    td {{
      padding: 0.65rem 1rem;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      vertical-align: middle;
    }}
    tr:hover td {{ background: rgba(212, 165, 116, 0.04); }}
    tr.row-fail td {{ border-left: 3px solid var(--fail); }}
    tr.row-pass td {{ border-left: 3px solid transparent; }}
    tr.row-pending td {{ border-left: 3px solid var(--pending); opacity: 0.92; }}
    tr.row-artifact td {{ border-left: 3px solid var(--artifact); }}
    .mono {{ font-family: ui-monospace, "Cascadia Code", monospace; }}
    .small {{ font-size: 0.8rem; }}
    .tiny {{ font-size: 0.72rem; max-width: 8rem; overflow: hidden; text-overflow: ellipsis; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .time {{ color: var(--muted); font-size: 0.75rem; }}
    .family {{
      font-size: 0.72rem;
      padding: 0.2rem 0.45rem;
      border-radius: 6px;
      background: rgba(255,255,255,0.06);
      color: var(--muted);
    }}
    .badge {{
      display: inline-block;
      padding: 0.25rem 0.55rem;
      border-radius: 999px;
      font-size: 0.68rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .badge.pass {{ background: var(--pass-bg); color: var(--pass); }}
    .badge.fail {{ background: var(--fail-bg); color: var(--fail); }}
    .badge.pending {{ background: var(--pending-bg); color: var(--pending); }}
    .badge.artifact {{ background: var(--artifact-bg); color: var(--artifact); }}
    .skip-link {{
      position: absolute;
      left: -9999px;
      top: 0.5rem;
      z-index: 100;
      padding: 0.45rem 0.9rem;
      background: var(--accent);
      color: #141210;
      font-weight: 700;
      font-size: 0.85rem;
      text-decoration: none;
      border-radius: 8px;
    }}
    .skip-link:focus {{
      left: 0.75rem;
      outline: 2px solid var(--text);
      outline-offset: 2px;
    }}
    .matrix-toolbar {{
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      justify-content: space-between;
      gap: 1rem 1.5rem;
      padding: 1rem 1.35rem;
      background: rgba(0,0,0,0.2);
      border-bottom: 1px solid var(--border);
    }}
    .matrix-filter label {{
      display: block;
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      margin-bottom: 0.35rem;
    }}
    .matrix-filter input {{
      min-width: min(100%, 220px);
      padding: 0.45rem 0.65rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text);
      font-family: inherit;
      font-size: 0.88rem;
    }}
    .export-links {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem 0.85rem;
      font-size: 0.8rem;
    }}
    .export-label {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 0.65rem;
      color: var(--muted);
      margin-right: 0.25rem;
    }}
    .export-links a {{
      color: var(--accent);
      font-weight: 600;
      text-decoration: none;
    }}
    .export-links a:hover {{ text-decoration: underline; }}
    .th-sort {{
      padding: 0.35rem 0.5rem;
      vertical-align: bottom;
    }}
    .sort-btn {{
      background: none;
      border: none;
      color: inherit;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      padding: 0;
      text-align: left;
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.35rem;
    }}
    .sort-btn:hover {{ color: var(--accent); }}
    .sort-ind {{
      font-size: 0.65rem;
      color: var(--accent);
      min-width: 1em;
    }}
    footer {{
      margin-top: 2.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
      font-size: 0.8rem;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <a class="skip-link" href="#briefing">Skip to briefing</a>
  <div class="wrap">
    <header>
      <h1>{_escape(title)}</h1>
      <p class="subtitle">Prime Intellect live coordination sweep — presentation bundle with briefing, comparative charts, and full method matrix. PASS reflects harness gates; read <strong>Analysis highlights</strong> and outcome metrics for task performance.</p>
      <div class="meta">
        <span><strong>Run dir</strong> {_escape(str(run_dir))}</span>
        <span><strong>Generated</strong> {_escape(generated_at)}</span>
        <span><strong>Catalog</strong> {total} methods</span>
      </div>
    </header>
    {nav_html}
    <div id="kpis">
    <div class="cards">
      <div class="card pass"><div class="label">Pass</div><div class="value">{pass_n}</div></div>
      <div class="card fail"><div class="label">Fail</div><div class="value">{fail_n}</div></div>
      <div class="card pending"><div class="label">Pending</div><div class="value">{pending_n}</div></div>
      <div class="card pending"><div class="label">Artifact only</div><div class="value">{artifact_n}</div></div>
      <div class="card total"><div class="label">Coverage</div><div class="value">{pass_n}/{total}</div></div>
    </div>
    <div class="cards kpi-deep">
      <div class="card total"><div class="label">Σ wall time</div><div class="value">{_escape(tw_card)}</div><div class="label" style="margin-top:0.35rem">hours</div></div>
      <div class="card total"><div class="label">Σ LLM calls</div><div class="value">{_escape(sc_card)}</div></div>
      <div class="card total"><div class="label">Σ meta tokens</div><div class="value">{_escape(st_card)}</div></div>
    </div>
    </div>
    {briefing_html}
    {insights_html}
    {charts_html}
    <section id="matrix" class="table-section">
      <div class="table-head">
        <h2>Method matrix</h2>
        <p>Throughput and resilience are episode means from <code class="mono">results.json</code>. Wall time uses <code class="mono">method_status</code> start/end. Click column headers to sort; filter narrows rows. Downloads are sibling files in this report folder.</p>
      </div>
      <div id="matrix-tools" class="matrix-toolbar" tabindex="-1">
        <div class="matrix-filter">
          <label for="ltg-matrix-filter">Filter by method id</label>
          <input id="ltg-matrix-filter" type="search" placeholder="Substring match…" autocomplete="off"/>
        </div>
        <div class="export-links">
          <span class="export-label">Export</span>
          <a href="methods_matrix.csv" download>methods_matrix.csv</a>
          <a href="snapshot.json" download>snapshot.json</a>
          <a href="analysis_summary.json" download>analysis_summary.json</a>
          <a href="manifest.json" download>manifest.json</a>
        </div>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="m" data-ltg-type="str">Method<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="fam" data-ltg-type="str">Family<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="st" data-ltg-type="str">Status<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="ws" data-ltg-type="num">Wall<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="mdl" data-ltg-type="str">Model<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="eps" data-ltg-type="num">Eps<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="thr" data-ltg-type="num">Ø thr<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="rsil" data-ltg-type="num">Ø resil<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="tc" data-ltg-type="num">Consign<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="lc" data-ltg-type="num">LLM calls<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="mt" data-ltg-type="num">Tokens<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="er" data-ltg-type="num">LLM err<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="end" data-ltg-type="str">Ended<span class="sort-ind" aria-hidden="true"></span></button></th>
              <th scope="col" class="th-sort"><button type="button" class="sort-btn" data-ltg-sort="art" data-ltg-type="str">Artifact<span class="sort-ind" aria-hidden="true"></span></button></th>
            </tr>
          </thead>
          <tbody id="ltg-method-tbody">
            {tbody}
          </tbody>
        </table>
      </div>
    </section>
    <footer>
      Pipeline: <span class="mono">python scripts/benchmark_suite.py publish --run-dir …</span>
      or <span class="mono">scripts/build_benchmark_report.py</span>.
      FAIL = strict live harness gates (tokens, error rate, invalid output).
    </footer>
    {matrix_script}
  </div>
</body>
</html>
"""


def generate_benchmark_report(
    run_dir: Path,
    *,
    scale_id: str = "medium_stress_signed_bus",
    out_dir: Path | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Build HTML report, machine snapshot, and analysis summary for one run directory."""
    run_dir = Path(run_dir).resolve()
    out_dir = Path(out_dir).resolve() if out_dir is not None else default_report_out_dir(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog = BUILTIN_COORDINATION_METHOD_IDS
    rows = build_rows(run_dir, scale_id, catalog)
    rows_sorted = sort_rows_for_table(rows)
    generated = datetime.now(UTC).isoformat()
    run_meta = load_run_meta(run_dir)
    run_summary = load_run_summary(run_dir)
    analytics = compute_run_analytics(rows)
    analytics_record = {
        **analytics,
        "schema_version": BENCHMARK_BUNDLE_SCHEMA_VERSION,
    }
    summary_counts = {
        "pass": sum(1 for r in rows if r["status"] == "PASS"),
        "fail": sum(1 for r in rows if r["status"] == "FAIL"),
        "pending": sum(1 for r in rows if r["status"] == "PENDING"),
        "artifact": sum(1 for r in rows if r["status"] == "ARTIFACT"),
    }
    git_hint = first_git_sha_from_rows(rows)

    snapshot = {
        "schema_version": BENCHMARK_BUNDLE_SCHEMA_VERSION,
        "generated_at": generated,
        "run_dir": str(run_dir),
        "scale_id": scale_id,
        "catalog_total": len(catalog),
        "summary": summary_counts,
        "analytics": analytics,
        "methods": rows,
    }
    (out_dir / "snapshot.json").write_text(
        json.dumps(snapshot, indent=2),
        encoding="utf-8",
    )
    (out_dir / "analysis_summary.json").write_text(
        json.dumps(analytics_record, indent=2),
        encoding="utf-8",
    )
    write_methods_matrix_csv(out_dir / "methods_matrix.csv", rows_sorted)
    manifest = build_presentation_manifest(
        schema_version=BENCHMARK_BUNDLE_SCHEMA_VERSION,
        generated_at=generated,
        run_dir=run_dir,
        scale_id=scale_id,
        analytics=analytics,
        summary_counts=summary_counts,
        git_sha_hint=git_hint,
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    report_title = title or "LabTrust Gym — Prime live coordination benchmark"
    html_out = render_html(
        rows,
        title=report_title,
        run_dir=run_dir,
        scale_id=scale_id,
        generated_at=generated,
        run_meta=run_meta,
        run_summary=run_summary,
        analytics=analytics,
    )
    index_path = out_dir / "index.html"
    index_path.write_text(html_out, encoding="utf-8")
    return {
        "index_html": index_path,
        "snapshot_json": out_dir / "snapshot.json",
        "analysis_json": out_dir / "analysis_summary.json",
        "matrix_csv": out_dir / "methods_matrix.csv",
        "manifest_json": out_dir / "manifest.json",
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HTML benchmark report from run artifacts.")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path("runs/pi_all_methods_full_live"),
        help="Directory containing method_status.jsonl and cell folders",
    )
    parser.add_argument(
        "--scale-id",
        type=str,
        default="medium_stress_signed_bus",
        help="Scale id used in cell folder names",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: sibling {run_name}_report)",
    )
    args = parser.parse_args()
    paths = generate_benchmark_report(
        args.run_dir,
        scale_id=args.scale_id,
        out_dir=args.out_dir,
    )
    print(f"Wrote {paths['index_html']}")
    print(f"Wrote {paths['snapshot_json']}")
    print(f"Wrote {paths['analysis_json']}")
    print(f"Wrote {paths['matrix_csv']}")
    print(f"Wrote {paths['manifest_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
