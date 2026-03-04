# Demo readiness

Checklist and notes to ensure the three presentation demos (Tier 1 full pipeline, Tier 2 no-network pipeline, Tier 3 compact official pack) run successfully. See [Hospital lab full pipeline](../benchmarks/hospital_lab_full_pipeline.md) (pathology lab / blood sciences pipeline) for scope and commands.

## Demo prerequisites (all tiers)

- **Policy:** From repo root, run `labtrust validate-policy`. Must exit 0. If not at repo root, set `LABTRUST_POLICY_DIR` to your policy directory.
- **Install:** `pip install -e ".[dev,env,plots]"`. For Tier 1 with live LLM add `.[llm_openai]` or `.[llm_anthropic]` and set the corresponding API keys.
- **CLI smoke:** `labtrust --version` and `labtrust quick-eval --seed 42` must succeed. Quick-eval is the minimal smoke for the benchmark stack.
- **CWD:** Run all commands from the repo root (or with `LABTRUST_POLICY_DIR` set). Otherwise you may see `PolicyPathError` (policy directory not found).

Before the presentation, run the verification script to confirm the environment is ready:

```bash
bash scripts/verify_demo_readiness.sh
```

On Windows (PowerShell):

```powershell
.\scripts\verify_demo_readiness.ps1
```

## Demo on Windows

On Windows, two system-level security attacks (SEC-COORD-MATRIX-001, SEC-COORD-PACK-MULTI-AGENTIC) can fail with a file-lock error on `episodes.jsonl` during the coordination pack run ("The process cannot access the file because it is being used by another process"). The agent/shield layer passes; the failure is environmental, not a control failure.

For a clean demo on Windows you can:

- Run the security suite standalone with `--skip-system-level` when demonstrating the attack suite (e.g. `labtrust run-security-suite --out <dir> --skip-system-level`). State that system-level coordination-under-attack was skipped.
- Or run the full pipeline or official pack and explain that the two reported failures are due to Windows file locking; re-run on Linux or macOS to confirm they pass.

## Export risk register from full pipeline output

The full pipeline writes coordination pack outputs under a subdirectory: `<out>/coordination_pack/pack_summary.csv`, `pack_gate.md`, etc. The risk register builder expects `pack_summary.csv` at the run dir root for coordination evidence. To include both top-level security/safety evidence and coordination pack evidence when building the risk register from full pipeline output, pass both the pipeline output root and the coordination_pack subdir:

```bash
labtrust export-risk-register --out <dir> --runs <full_out> --runs <full_out>/coordination_pack
```

Example: if you ran `python scripts/run_hospital_lab_full_pipeline.py --out demo_out/full --include-coordination-pack`, then:

```bash
labtrust export-risk-register --out demo_out/risk_out --runs demo_out/full --runs demo_out/full/coordination_pack
```

## Verification chain (trustworthiness demo)

The full pipeline output does not contain `receipts/` (EvidenceBundles). Only `labtrust package-release` produces those. For the verify-release step of the demo, use a separate package-release run:

```bash
labtrust package-release --profile minimal --seed-base 100 --out demo_out/release
labtrust export-risk-register --out demo_out/release --runs demo_out/release
labtrust build-release-manifest --release-dir demo_out/release
labtrust verify-release --release-dir demo_out/release --strict-fingerprints
```

See [Trust verification](../risk-and-security/trust_verification.md) and [CI](../operations/ci.md) for the full E2E chain.

## See also

- [Recommended Windows setup](windows_setup.md) — Path, shell, and `--skip-system-level` for Windows.
- [Quick demos](quick_demos.md) — Canonical demo commands and success criteria.
- [Hospital lab full pipeline](../benchmarks/hospital_lab_full_pipeline.md) — Full pipeline scope and options.
- [Trust verification](../risk-and-security/trust_verification.md) — Verification chain and EvidenceBundles.
