from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.coordination.registry import (
    BUILTIN_COORDINATION_METHOD_IDS,
)
from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
from labtrust_gym.benchmarks.runner import run_benchmark


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _set_default_heartbeat_env(
    step_every: int,
    step_every_s: float,
    ep_every: int,
) -> None:
    os.environ.setdefault("LABTRUST_STEP_HEARTBEAT_EVERY_STEPS", str(step_every))
    os.environ.setdefault("LABTRUST_STEP_HEARTBEAT_EVERY_S", str(step_every_s))
    os.environ.setdefault("LABTRUST_BENCH_HEARTBEAT_EVERY_EP", str(ep_every))


def _strict_checks(
    row: dict[str, Any],
    data: dict[str, Any],
    method: str,
    *,
    max_llm_error_rate: float,
) -> None:
    ep = (data.get("episodes") or [{}])[0]
    llm_ep = ep.get("llm_episode") or {}
    llm_metrics = (
        ((ep.get("metrics") or {}).get("coordination") or {}).get("llm")
        or {}
    )
    md = data.get("metadata") or {}
    row.update(
        {
            "pipeline_mode": data.get("pipeline_mode"),
            "llm_backend_id": data.get("llm_backend_id"),
            "llm_model_id": data.get("llm_model_id"),
            "llm_calls": llm_ep.get("total_calls"),
            "llm_errors": llm_ep.get("error_count"),
            "llm_error_rate": llm_ep.get("error_rate"),
            "episode_total_tokens": llm_ep.get("total_tokens"),
            "metadata_total_tokens": md.get("total_tokens"),
            "invalid_output_rate": llm_metrics.get("invalid_output_rate"),
        }
    )
    checks = [
        data.get("pipeline_mode") == "llm_live",
        data.get("llm_backend_id") == "prime_intellect_live",
    ]
    if method.startswith("llm_"):
        err_rate = llm_ep.get("error_rate")
        try:
            err_rate_ok = float(err_rate or 0.0) <= max_llm_error_rate
        except (TypeError, ValueError):
            err_rate_ok = False
        tokens_reported = (md.get("total_tokens") or 0) > 0
        calls_reported = (llm_ep.get("total_calls") or 0) > 0
        mean_lat_raw = llm_ep.get("mean_latency_ms")
        sum_lat_raw = llm_ep.get("sum_latency_ms")
        try:
            mean_lat_ok = float(mean_lat_raw or 0.0) > 0.0
        except (TypeError, ValueError):
            mean_lat_ok = False
        try:
            sum_lat_ok = float(sum_lat_raw or 0.0) > 0.0
        except (TypeError, ValueError):
            sum_lat_ok = False
        # Some OpenAI-compatible providers may omit token usage in tool paths.
        # Require positive call count plus either token or latency evidence.
        live_activity_ok = calls_reported and (tokens_reported or mean_lat_ok or sum_lat_ok)
        checks.extend(
            [
                calls_reported,
                err_rate_ok,
                live_activity_ok,
                llm_metrics.get("invalid_output_rate") in (0, 0.0, None),
            ]
        )
    row["status"] = "PASS" if all(checks) else "FAIL"
    if not all(checks):
        row["reason"] = "strict_checks_failed"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run all coordination methods in full Prime live mode with crash-safe "
            "per-method persistence and detailed heartbeats."
        )
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("runs/pi_all_methods_full_live"),
    )
    parser.add_argument("--scale-id", type=str, default="medium_stress_signed_bus")
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7000)
    parser.add_argument(
        "--model",
        type=str,
        default="anthropic/claude-3.5-haiku",
    )
    parser.add_argument("--max-attempts-llm", type=int, default=2)
    parser.add_argument("--max-llm-error-rate", type=float, default=0.05)
    parser.add_argument("--step-heartbeat-every-steps", type=int, default=25)
    parser.add_argument("--step-heartbeat-every-s", type=float, default=45.0)
    parser.add_argument("--bench-heartbeat-every-ep", type=int, default=1)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--publish-report",
        action="store_true",
        help=(
            "After the sweep finishes, run scripts/build_benchmark_report.py on this "
            "out-dir (partial runs still get a useful bundle)."
        ),
    )
    parser.add_argument("--methods", nargs="+", default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if args.out_dir.is_absolute():
        out_dir = args.out_dir.resolve()
    else:
        out_dir = (root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    _set_default_heartbeat_env(
        step_every=args.step_heartbeat_every_steps,
        step_every_s=args.step_heartbeat_every_s,
        ep_every=args.bench_heartbeat_every_ep,
    )

    methods = (
        list(args.methods)
        if args.methods
        else list(BUILTIN_COORDINATION_METHOD_IDS)
    )
    rows_path = out_dir / "all_methods_full_table.json"
    status_log_path = out_dir / "method_status.jsonl"
    run_meta_path = out_dir / "run_meta.json"

    rows: list[dict[str, Any]] = []
    if not args.no_resume and rows_path.exists():
        try:
            loaded = json.loads(rows_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                rows = [r for r in loaded if isinstance(r, dict)]
        except Exception:
            rows = []
    done_pass = {
        str(r.get("method"))
        for r in rows
        if r.get("status") == "PASS" and r.get("method")
    }

    run_meta = {
        "started_at": _now_iso(),
        "scale_id": args.scale_id,
        "episodes": args.episodes,
        "seed": args.seed,
        "llm_backend": "prime_intellect_live",
        "model": args.model,
        "resume_enabled": not args.no_resume,
        "methods_count": len(methods),
    }
    _atomic_write_json(run_meta_path, run_meta)

    for i, method in enumerate(methods):
        if method in done_pass:
            print(
                f"[{i + 1}/{len(methods)}] {method}: SKIP (already PASS)",
                flush=True,
            )
            continue

        if method.startswith("llm_"):
            max_attempts = max(1, args.max_attempts_llm)
        else:
            max_attempts = 1
        row: dict[str, Any] = {"method": method, "status": "FAIL"}
        for attempt in range(1, max_attempts + 1):
            row = {
                "method": method,
                "attempt": attempt,
                "started_at": _now_iso(),
                "status": "FAIL",
            }
            _append_jsonl(status_log_path, {"event": "method_start", **row})
            try:
                scale_cfg = load_scale_config_by_id(root, args.scale_id)
                if method.startswith("llm_"):
                    scale_cfg.coord_propose_actions_max_agents = max(
                        getattr(scale_cfg, "num_agents_total", 0),
                        100_000,
                    )
                if method == "llm_constrained":
                    os.environ["LABTRUST_LLM_CONSTRAINED_MAX_AGENTS_PER_STEP"] = "8"
                else:
                    os.environ.pop("LABTRUST_LLM_CONSTRAINED_MAX_AGENTS_PER_STEP", None)
                cell_dir = out_dir / f"{args.scale_id}_{method}_none"
                cell_dir.mkdir(parents=True, exist_ok=True)
                results_path = cell_dir / "results.json"
                episode_log_path = cell_dir / "episodes.jsonl"

                run_benchmark(
                    task_name="coord_risk",
                    num_episodes=args.episodes,
                    base_seed=args.seed + i + (attempt - 1) * 10000,
                    out_path=results_path,
                    repo_root=root,
                    log_path=episode_log_path,
                    coord_method=method,
                    injection_id="none",
                    scale_config_override=scale_cfg,
                    llm_backend="prime_intellect_live",
                    llm_model=args.model,
                    allow_network=True,
                )
                data = json.loads(results_path.read_text(encoding="utf-8"))
                _strict_checks(
                    row,
                    data,
                    method,
                    max_llm_error_rate=max(0.0, float(args.max_llm_error_rate)),
                )
                row["ended_at"] = _now_iso()
                row["result_path"] = str(results_path)
                _append_jsonl(status_log_path, {"event": "method_end", **row})
                if row["status"] == "PASS":
                    break
            except Exception as exc:  # noqa: BLE001
                row.update(
                    {
                        "status": "FAIL",
                        "reason": str(exc)[:220],
                        "trace": traceback.format_exc()[:2000],
                        "ended_at": _now_iso(),
                    }
                )
                _append_jsonl(status_log_path, {"event": "method_end", **row})

        rows = [r for r in rows if r.get("method") != method]
        rows.append(row)
        _atomic_write_json(rows_path, rows)
        print(f"[{i + 1}/{len(methods)}] {method}: {row['status']}", flush=True)

    final = {
        "completed_at": _now_iso(),
        "total_methods": len(methods),
        "pass_count": sum(1 for r in rows if r.get("status") == "PASS"),
        "fail_count": sum(1 for r in rows if r.get("status") != "PASS"),
        "table_path": str(rows_path),
        "status_log_path": str(status_log_path),
    }
    _atomic_write_json(out_dir / "run_summary.json", final)
    print(f"WROTE {rows_path}", flush=True)
    print(f"WROTE {out_dir / 'run_summary.json'}", flush=True)
    exit_code = 0 if final["fail_count"] == 0 else 2
    if args.publish_report:
        report_script = root / "scripts" / "build_benchmark_report.py"
        cmd = [
            sys.executable,
            str(report_script),
            "--run-dir",
            str(out_dir),
            "--scale-id",
            args.scale_id,
        ]
        print(f"PUBLISH_REPORT {' '.join(cmd)}", flush=True)
        proc = subprocess.run(cmd, cwd=str(root))
        if proc.returncode != 0:
            print(
                f"warning: report step exited {proc.returncode}",
                flush=True,
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
