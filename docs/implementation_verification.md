# Implementation verification (safety case and controls)

The **safety case** maps high-level claims to controls, tests, artifacts, and verification commands. It provides an auditable trail from "what we claim" to "how we verify it."

## Claims and policy

- **Policy file:** `policy/safety_case/claims.v0.1.yaml` defines claims, each with:
  - Claim identifier and description
  - Associated controls (e.g. RBAC, hashchain, invariant enforcement)
  - Test or scenario reference
  - Artifact (e.g. golden scenario log, evidence bundle)
  - Verification command (e.g. `labtrust validate-policy`, `pytest tests/test_golden_suite.py`)

The generator in `src/labtrust_gym/security/safety_case.py` reads this policy and emits a structured safety case.

## CLI

```bash
labtrust safety-case --out <dir>
```

Writes under `<dir>/SAFETY_CASE/`:

- **safety_case.json** — Machine-readable: claims, controls, tests, artifacts, commands.
- **safety_case.md** — Human-readable summary for reviewers.

## Where it is used

- **package-release (paper_v0.1):** The paper profile runs the safety case generator and writes `SAFETY_CASE/` into the release directory alongside SECURITY/, receipts, and FIGURES/.
- **run-official-pack:** When running the official benchmark pack, the pack runner can emit the safety case into the same output directory so the full artifact set (baselines, SECURITY, SAFETY_CASE, transparency log) is in one place.

## Implementation status

For what is implemented vs tested vs remaining gaps (official pack v0.2, llm_live, plumbing checks), see [STATUS](STATUS.md).

## See also

- [Risk register](risk_register.md) — Bundle and controls; safety-case claims feed into control lists.
- [Risk register contract](risk_register_contract.v0.1.md) — `controls` and `source: safety_case`.
- [Official benchmark pack](official_benchmark_pack.md) — Pack contents and required_reports (including safety_case).
