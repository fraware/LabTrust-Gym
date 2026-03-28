from __future__ import annotations

import json
import traceback
from pathlib import Path

from labtrust_gym.baselines.coordination.registry import BUILTIN_COORDINATION_METHOD_IDS
from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
from labtrust_gym.benchmarks.runner import run_benchmark


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "runs" / "pi_all_methods_smoke"
    out.mkdir(parents=True, exist_ok=True)

    methods = list(BUILTIN_COORDINATION_METHOD_IDS)
    rows: list[dict[str, object]] = []

    for i, method in enumerate(methods):
        row: dict[str, object] = {"method": method}
        max_attempts = 3 if method.startswith("llm_") else 1
        for attempt in range(1, max_attempts + 1):
            try:
                scale_cfg = load_scale_config_by_id(root, "small_smoke")
                scale_cfg.horizon_steps = 8
                cell_dir = out / f"small_smoke_{method}_none"
                cell_dir.mkdir(parents=True, exist_ok=True)

                run_benchmark(
                    task_name="coord_risk",
                    num_episodes=1,
                    base_seed=1200 + i + (attempt - 1) * 10000,
                    out_path=cell_dir / "results.json",
                    repo_root=root,
                    log_path=cell_dir / "episodes.jsonl",
                    coord_method=method,
                    injection_id="none",
                    scale_config_override=scale_cfg,
                    llm_backend="prime_intellect_live",
                    llm_model="anthropic/claude-3.5-haiku",
                    allow_network=True,
                )

                data = json.loads((cell_dir / "results.json").read_text(encoding="utf-8"))
                episode = (data.get("episodes") or [{}])[0]
                llm_ep = episode.get("llm_episode") or {}
                llm_metrics = ((episode.get("metrics") or {}).get("coordination") or {}).get("llm") or {}
                metadata = data.get("metadata") or {}

                row.update(
                    {
                        "status": "PASS",
                        "attempts": attempt,
                        "pipeline_mode": data.get("pipeline_mode"),
                        "llm_backend_id": data.get("llm_backend_id"),
                        "llm_model_id": data.get("llm_model_id"),
                        "llm_calls": llm_ep.get("total_calls"),
                        "llm_errors": llm_ep.get("error_count"),
                        "llm_error_rate": llm_ep.get("error_rate"),
                        "episode_total_tokens": llm_ep.get("total_tokens"),
                        "metadata_total_tokens": metadata.get("total_tokens"),
                        "invalid_output_rate": llm_metrics.get("invalid_output_rate"),
                    }
                )
                row.pop("reason", None)
                row.pop("trace", None)

                checks = [
                    data.get("pipeline_mode") == "llm_live",
                    data.get("llm_backend_id") == "prime_intellect_live",
                ]
                if method.startswith("llm_"):
                    checks.extend(
                        [
                            (llm_ep.get("total_calls") or 0) > 0,
                            (llm_ep.get("error_count") or 0) == 0,
                            (metadata.get("total_tokens") or 0) > 0,
                            llm_metrics.get("invalid_output_rate") in (0, 0.0, None),
                        ]
                    )
                if all(checks):
                    break
                row["status"] = "FAIL"
                row["reason"] = "strict_checks_failed"
            except Exception as exc:  # noqa: BLE001
                row.update(
                    {
                        "status": "FAIL",
                        "attempts": attempt,
                        "reason": str(exc)[:220],
                        "trace": traceback.format_exc()[:1500],
                    }
                )
            if attempt == max_attempts:
                break

        rows.append(row)
        print(f"[{i + 1}/{len(methods)}] {method}: {row['status']}", flush=True)

    out_path = out / "all_methods_smoke_table.json"
    out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"WROTE {out_path}", flush=True)


if __name__ == "__main__":
    main()
