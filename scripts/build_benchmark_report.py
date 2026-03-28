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
    }


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


def _escape(s: Any) -> str:
    return html.escape(str(s) if s is not None else "", quote=True)


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
        res_file = Path(rpath) if rpath else _cell_results_path(run_dir, scale_id, method)
        enrich = _enrich_results(res_file)
        if end:
            status = str(end.get("status") or "UNKNOWN")
            ended_at = end.get("ended_at")
            reason = end.get("reason")
        elif enrich:
            status = "ARTIFACT"
            ended_at = None
            reason = "results.json on disk; no matching method_end in log"
        else:
            status = "PENDING"
            ended_at = None
            reason = None

        rows.append(
            {
                "method": method,
                "family": "llm" if is_llm else "classical",
                "status": status,
                "ended_at": ended_at,
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


def render_html(
    rows: list[dict[str, Any]],
    *,
    title: str,
    run_dir: Path,
    scale_id: str,
    generated_at: str,
) -> str:
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

        return f"""<tr class="row-{st.lower()}">
<td class="mono method-name">{_escape(r["method"])}</td>
<td><span class="family">{_escape(r["family"])}</span></td>
<td><span class="{badge_class}"{badge_title}>{_escape(st)}</span></td>
<td class="mono small">{_escape(mdl)}</td>
<td class="num">{_fmt_num(episodes)}</td>
<td class="num">{_fmt_num(tp, digits=3)}</td>
<td class="num">{_fmt_num(r.get('llm_calls'))}</td>
<td class="num">{_fmt_num(r.get('metadata_total_tokens'))}</td>
<td class="num">{err_cell}</td>
<td class="small time">{_escape(r.get('ended_at') or '—')}</td>
<td class="mono tiny" title="{_escape(rp)}">{_escape(short_path or '—')}</td>
</tr>"""

    rows_sorted = sorted(
        rows,
        key=lambda x: (
            0 if x["status"] == "FAIL" else 1 if x["status"] == "PENDING" else 2,
            x["family"],
            x["method"],
        ),
    )
    tbody = "\n".join(row_html(r) for r in rows_sorted)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
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
  <div class="wrap">
    <header>
      <h1>{_escape(title)}</h1>
      <p class="subtitle">Composite coordination benchmark from recorded runs: latest <code class="mono">method_end</code> per method, enriched from <code class="mono">results.json</code> where present. Scale <strong>{_escape(scale_id)}</strong>, Prime Intellect live path.</p>
      <div class="meta">
        <span><strong>Run dir</strong> {_escape(str(run_dir))}</span>
        <span><strong>Generated</strong> {_escape(generated_at)}</span>
        <span><strong>Catalog</strong> {total} methods</span>
      </div>
    </header>
    <div class="cards">
      <div class="card pass"><div class="label">Pass</div><div class="value">{pass_n}</div></div>
      <div class="card fail"><div class="label">Fail</div><div class="value">{fail_n}</div></div>
      <div class="card pending"><div class="label">Pending</div><div class="value">{pending_n}</div></div>
      <div class="card pending"><div class="label">Artifact only</div><div class="value">{artifact_n}</div></div>
      <div class="card total"><div class="label">Coverage</div><div class="value">{pass_n}/{total}</div></div>
    </div>
    <section class="table-section">
      <div class="table-head">
        <h2>Method matrix</h2>
        <p>Throughput is mean over episodes in each <code class="mono">results.json</code>. LLM columns reflect the latest logged run.</p>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Method</th>
              <th>Family</th>
              <th>Status</th>
              <th>Model</th>
              <th>Eps</th>
              <th>Ø throughput</th>
              <th>LLM calls</th>
              <th>Tokens (meta)</th>
              <th>LLM err rate</th>
              <th>Ended (UTC)</th>
              <th>Artifact</th>
            </tr>
          </thead>
          <tbody>
            {tbody}
          </tbody>
        </table>
      </div>
    </section>
    <footer>
      Produced by <span class="mono">scripts/build_benchmark_report.py</span>. Regenerate after new runs to refresh. FAIL rows include strict-gate failures (tokens, error rate, invalid output).
    </footer>
  </div>
</body>
</html>
"""


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
        default=Path("runs/pi_benchmark_report"),
        help="Output directory for index.html and snapshot.json",
    )
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog = BUILTIN_COORDINATION_METHOD_IDS
    rows = build_rows(run_dir, args.scale_id, catalog)
    generated = datetime.now(UTC).isoformat()

    snapshot = {
        "generated_at": generated,
        "run_dir": str(run_dir),
        "scale_id": args.scale_id,
        "catalog_total": len(catalog),
        "summary": {
            "pass": sum(1 for r in rows if r["status"] == "PASS"),
            "fail": sum(1 for r in rows if r["status"] == "FAIL"),
            "pending": sum(1 for r in rows if r["status"] == "PENDING"),
            "artifact": sum(1 for r in rows if r["status"] == "ARTIFACT"),
        },
        "methods": rows,
    }
    (out_dir / "snapshot.json").write_text(
        json.dumps(snapshot, indent=2),
        encoding="utf-8",
    )

    title = "LabTrust Gym — Prime live coordination benchmark"
    html_out = render_html(
        rows,
        title=title,
        run_dir=run_dir,
        scale_id=args.scale_id,
        generated_at=generated,
    )
    (out_dir / "index.html").write_text(html_out, encoding="utf-8")
    print(f"Wrote {out_dir / 'index.html'}")
    print(f"Wrote {out_dir / 'snapshot.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
