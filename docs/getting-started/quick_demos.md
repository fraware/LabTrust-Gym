# Quick demos

Single place for "If you want to see X, run Y." All demos are deterministic; run from the repo root (or set `LABTRUST_POLICY_DIR` to your policy directory). For a one-line entry point by goal, see the "I want to..." table in [Getting started](index.md) or the README.

## Canonical demo commands

| Goal | Command | Approx. time |
|------|---------|--------------|
| See quick sanity check | `labtrust quick-eval --seed 42` | ~1 min |
| See one-line run stats (episodes, steps, violations, throughput) | `labtrust run-summary --run <dir>` (use `--format json` for machine-readable) | seconds |
| See full forker pipeline (validate → coordination pack → risk register) | `labtrust forker-quickstart --out labtrust_runs/forker_quickstart` | ~5–15 min |
| See coordination + security evidence (official pack with coordination pack) | `labtrust run-official-pack --out <dir> --seed-base 100 --include-coordination-pack` | ~10–15 min |
| See paper-ready artifact and verify it | `labtrust package-release --profile paper_v0.1 --seed-base 100 --out <dir>` then `labtrust verify-release --release-dir <dir> --strict-fingerprints` | ~15+ min |
| Export UI bundle (tables + coordination charts) for portal | After a run with coordination output: `labtrust ui-export --run <dir> --out <zip>`. Zip contains `index.json`, `coordination_artifacts`, and `coordination/graphs/` HTML charts. See [Frontend handoff](../reference/frontend_handoff_ui_bundle.md). | seconds |

### What success looks like

- **Quick sanity check:** Exit code 0; a markdown summary is printed and logs appear under `./labtrust_runs/quick_eval_<timestamp>/` (including `summary.md`).
- **Forker quickstart:** Exit code 0; output dir contains `pack/pack_summary.csv`, `pack/pack_gate.md`, and `risk_out/RISK_REGISTER_BUNDLE.v0.1.json`. You can inspect gate verdicts in `pack_gate.md`.
- **Official pack with coordination pack:** Exit code 0; output dir has baselines, `SECURITY/`, `SAFETY_CASE/`, and (with `--include-coordination-pack`) a coordination pack with `pack_summary.csv` and `pack_gate.md`. Run `labtrust ui-export --run <dir> --out <zip>` to produce a UI bundle with coordination_artifacts and `coordination/graphs/` HTML charts for the portal ([Frontend handoff](../reference/frontend_handoff_ui_bundle.md)).
- **Paper-ready artifact and verify:** `package-release` exits 0 and writes the release to `<dir>`. `verify-release` prints a summary and exits 0; all EvidenceBundles and RELEASE_MANIFEST validate.

## See also

- [Demo readiness](demo_readiness.md) — Prerequisites, Windows notes, and export-risk-register for full pipeline output.
- [Forker guide](forkers.md) — End-to-end stories and demo scenarios by partner.
- [Paper provenance](../benchmarks/paper/README.md) — Reference demonstration for external reviewers.
- [Trust verification](../risk-and-security/trust_verification.md) and [CI](../operations/ci.md) — E2E verification chain.
