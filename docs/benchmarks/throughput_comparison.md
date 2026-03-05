# Throughput-focused comparison

When the main metric of interest is **throughput** (number of specimen releases per episode), use the **throughput_sla** task rather than the coordination pack. The coordination pack (coord_risk) is designed for safety, security, and resilience under injections; its cells may report zero throughput until coordination methods and scale setup produce release-capable work (see [Coordination benchmark card](../coordination/coordination_benchmark_card.md) and the non-zero throughput plan).

## Recommended path: throughput_sla task

1. **Run the benchmark** with the scripted baseline (default for throughput_sla in the baseline registry):

   ```bash
   labtrust run-benchmark --task throughput_sla --num-episodes 10 --out ./out/throughput_sla.json
   ```

   The baseline registry maps `throughput_sla` to `scripted_ops_v1` (scripted agents that perform accept, process, and release). No coordination method is used; the task uses a fixed set of scripted agents and an initial state with specimens already in `accepted` status.

2. **Read throughput from the result** JSON: each episode in `results.json` has `episodes[].metrics.throughput` (count of RELEASE_RESULT per episode). Aggregate as needed (e.g. mean over episodes).

3. **Optional:** Use `labtrust throughput-compare` to run throughput_sla with default 10 episodes and print mean throughput (writes `throughput_compare_results.json` by default; use `--episodes N` and `--out <path>` to customize).

4. **Optional:** Use `labtrust run-summary --run <dir>` or `labtrust summarize-results` to get one-line or tabular stats including throughput for a run directory.

## Optional: kernel coordination on throughput-like setup

If you want to compare a coordination method (e.g. kernel_auction_whca) on a setup that can produce releases, use the **coord_scale** or **coord_risk** task only after ensuring the scale has non-empty device queues (e.g. pre-populated initial queues or a reception path that enqueues work). See the coordination benchmark card and scale operational limits for scale configs and horizon_steps. The coordination pack’s default scales (small_smoke, medium_stress_signed_bus) require initial queue population or coordinator-driven accept/queue actions to achieve non-zero throughput.

## See also

- [Coordination benchmark card](../coordination/coordination_benchmark_card.md) – perf.throughput definition and when the pack reports it.
- [Benchmark card](benchmark_card.md) – throughput_sla task and baselines.
- [Official benchmark pack](official_benchmark_pack.md) – full pipeline including throughput_sla baseline runs.
