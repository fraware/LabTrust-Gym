# Recommended Windows setup

Single reference for running LabTrust-Gym on Windows: path, shell, known issues, and optional `--skip-system-level` for demos.

## Path

- Use a **short path without spaces or accented characters** (e.g. `C:\LabTrust-Gym`). Paths with spaces or special characters can cause issues in scripts and subprocesses.
- If policy lives elsewhere, set `LABTRUST_POLICY_DIR` to the policy directory (the directory that contains `emits/`, `schemas/`, etc.).

See [Installation — Paths with spaces or special characters](installation.md#paths-with-spaces-or-special-characters) for quoted paths and `REPO_ROOT`.

## Shell

- **PowerShell** is recommended for the project’s Windows scripts: `scripts\verify_demo_readiness.ps1`, `scripts\run_external_reviewer_risk_register_checks.ps1`, and other `.ps1` scripts.
- For Bash scripts (e.g. `scripts/verify_demo_readiness.sh`), use **Git Bash** or **WSL** and run from the repo root (or set `LABTRUST_POLICY_DIR`).

## Known issues

### File locking (coordination pack)

On Windows, two system-level security attacks (**SEC-COORD-MATRIX-001**, **SEC-COORD-PACK-MULTI-AGENTIC**) can fail with a file-lock error on `episodes.jsonl` during the coordination pack run (“The process cannot access the file because it is being used by another process”). The agent/shield layer passes; the failure is environmental, not a control failure.

**Mitigation for demos:**

- Run the security suite with **`--skip-system-level`** when demonstrating the attack suite (e.g. `labtrust run-security-suite --out <dir> --skip-system-level`). State that system-level coordination-under-attack was skipped.
- Or run the full pipeline or official pack and explain that the two reported failures are due to Windows file locking; re-run on Linux or macOS to confirm they pass.

See [Demo readiness](demo_readiness.md#demo-on-windows) for the same notes in the demo context.

### Locale and encoding

If you see encoding errors (e.g. when reading policy or logs), set UTF-8 for the process:

- **PowerShell:** `$env:PYTHONUTF8 = "1"`
- Or use a UTF-8 locale in your system/terminal.

## See also

- [Demo readiness](demo_readiness.md) — Prerequisites and verification script (including PowerShell).
- [Installation](installation.md) — Paths with spaces, `LABTRUST_POLICY_DIR`, and optional extras.
- [State of the art and limits](../reference/state_of_the_art_and_limits.md) — Windows path and locale note.
