# Demo pipeline results report

This report summarizes the full demo pipeline runs executed for the LabTrust-Gym presentation and Lovable portal. All commands were run from the repository root on Windows.

## Code improvements applied

1. **UI export for full-pipeline layout** — `ui-export` now accepts the hospital lab full-pipeline output (baselines/, SECURITY/, SAFETY_CASE/, optional coordination_pack/). Use `labtrust ui-export --run <full_out_dir> --out <zip>` to produce a UI bundle without going through package-release.
2. **Pack summary resilience** — The coordination security pack (sequential path) now catches per-cell exceptions and appends a minimal row for failed cells so `pack_summary.csv` and `pack_gate.md` are always written after all cells are attempted. Partial runs still produce a summary and gate.
3. **LLM live pack** — Run with `--pipeline-mode llm_live --allow-network --llm-backend openai_live`; add the pack output to the risk register when complete so the bundle can show `evidence_level: with_live_llm`.

## Commands executed

| Step | Command | Exit | Notes |
|------|---------|------|--------|
| Policy validation | `labtrust validate-policy` | 0 | Policy OK |
| Coordination security pack | `labtrust run-coordination-security-pack --out demo_video_out/coord_pack --matrix-preset hospital_lab --scale-ids small_smoke --seed 42` | 0 | ~96 s; pack_summary.csv, pack_gate.md written |
| Lab coordination report | `labtrust build-lab-coordination-report --pack-dir demo_video_out/coord_pack --matrix-preset hospital_lab` | 0 | LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.* |
| Risk register (full + coord) | `labtrust export-risk-register --out demo_video_out/risk_out --runs demo_video_out/full --runs demo_video_out/coord_pack` | 0 | RISK_REGISTER_BUNDLE.v0.1.json |
| Coverage validation | `labtrust validate-coverage --bundle demo_video_out/risk_out/RISK_REGISTER_BUNDLE.v0.1.json --out demo_video_out/risk_out` | 0 | |
| Package release | `labtrust package-release --profile minimal --seed-base 42 --out demo_video_out/release` | 0 | ~81 s; receipts/, EvidenceBundles |
| Risk register (release) | `labtrust export-risk-register --out demo_video_out/release --runs demo_video_out/release` | 0 | |
| Release manifest | `labtrust build-release-manifest --release-dir demo_video_out/release` | 0 | RELEASE_MANIFEST.v0.1.json |
| Verify release | `labtrust verify-release --release-dir demo_video_out/release --strict-fingerprints` | 0 | 8 EvidenceBundles passed |
| UI export (release) | `labtrust ui-export --run demo_video_out/release --out demo_video_out/release_ui_bundle.zip` | 0 | For portal consumption |
| UI export (full-pipeline) | `labtrust ui-export --run demo_video_out/full --out demo_video_out/full_ui_bundle.zip` | 0 | Full-pipeline layout now supported by ui-export |

## Full pipeline (background)

The hospital lab full pipeline was started with:

```powershell
python scripts/run_hospital_lab_full_pipeline.py --out demo_video_out/full --matrix-preset hospital_lab --security smoke --include-coordination-pack --seed-base 42
```

It produced: `demo_video_out/full/baselines/`, `demo_video_out/full/SECURITY/`, `demo_video_out/full/SAFETY_CASE/`, `demo_video_out/full/TRANSPARENCY_LOG/`, `demo_video_out/full/coordination_pack/pack_results/`. On Windows the script uses `skip_system_level=True` to avoid file-lock issues on system-level security cells. The coordination pack subdir contains per-cell results; a standalone coordination pack run was used to obtain `pack_summary.csv` and `pack_gate.md` in `demo_video_out/coord_pack`.

## Artifact layout

```
demo_video_out/
  full/                    # Full pipeline output (baselines, SECURITY, SAFETY_CASE, coordination_pack)
  coord_pack/              # Coordination security pack (pack_summary.csv, pack_gate.md, LAB_COORDINATION_REPORT.md)
  risk_out/                # Risk register bundle from full + coord_pack
  release/                 # package-release output (receipts, EvidenceBundles, RISK_REGISTER, RELEASE_MANIFEST)
  release_ui_bundle.zip    # UI bundle for portal (from release)
  DEMO_RESULTS_REPORT.md   # This file
  LOVABLE_SETUP.md         # How to connect the Lovable portal to this data
```

## Trust verification

- **verify-release:** 8 EvidenceBundles under `demo_video_out/release/receipts/` passed (schema, hashes, hashchain, invariant traces).
- **Risk register:** Built from full run and coord_pack; includes evidence links and coverage status.
- **Pack gate:** See `demo_video_out/coord_pack/pack_gate.md` for per-cell verdicts (PASS / FAIL / not_supported). Some cells show FAIL where violations exceed nominal+5 (e.g. INJ-COMMS-POISON-001); others PASS (e.g. INJ-ID-SPOOF-001 blocked).

## Coordination methods and metrics

The coordination pack (`coord_pack`) ran scale `small_smoke` with methods: `kernel_auction_whca_shielded`, `llm_repair_over_kernel_whca`, `llm_local_decider_signed_bus`, `llm_detector_throttle_advisor`. Injections include `none`, `INJ-ID-SPOOF-001`, `INJ-COMMS-POISON-001`, `INJ-COORD-PROMPT-INJECT-001`, `INJ-COORD-PLAN-REPLAY-001`, `INJ-COORD-BID-SHILL-001`. Metrics in `pack_summary.csv`: throughput, violations_total, blocks_total, sec.attack_success_rate, sec.detection_latency_steps, etc.

## LLM live pipeline

LLM live pack was started with:

```powershell
labtrust run-official-pack --out demo_video_out/pack_llm --seed-base 42 --pipeline-mode llm_live --allow-network --llm-backend openai_live --include-coordination-pack
```

When it completes, add it to the risk register:

```powershell
labtrust export-risk-register --out demo_video_out/risk_out --runs demo_video_out/full --runs demo_video_out/coord_pack --runs demo_video_out/pack_llm --runs demo_video_out/pack_llm/coordination_pack
```

Requires `OPENAI_API_KEY` in `.env` (or environment) and `pip install -e ".[llm_openai]"`. Do not commit `.env`; it is gitignored.

## Reproduce

From repo root:

```powershell
labtrust validate-policy
labtrust run-coordination-security-pack --out demo_video_out/coord_pack --matrix-preset hospital_lab --scale-ids small_smoke --seed 42
labtrust build-lab-coordination-report --pack-dir demo_video_out/coord_pack --matrix-preset hospital_lab
labtrust export-risk-register --out demo_video_out/risk_out --runs demo_video_out/full --runs demo_video_out/coord_pack
labtrust package-release --profile minimal --seed-base 42 --out demo_video_out/release
labtrust export-risk-register --out demo_video_out/release --runs demo_video_out/release
labtrust build-release-manifest --release-dir demo_video_out/release
labtrust verify-release --release-dir demo_video_out/release --strict-fingerprints
labtrust ui-export --run demo_video_out/release --out demo_video_out/release_ui_bundle.zip
```
