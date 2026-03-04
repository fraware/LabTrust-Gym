# Uncertainty quantification

Definitions and mapping of benchmark metrics to **epistemic** vs **aleatoric** uncertainty for downstream analysis and reporting.

## Definitions

- **Epistemic uncertainty** (model/estimate uncertainty): Uncertainty due to limited knowledge or estimation. Examples: LLM confidence scores, detector probability outputs, bootstrap CI half-width (uncertainty in the estimated mean), ECE/MCE (calibration of predicted probabilities).
- **Aleatoric uncertainty** (environment/stochastic): Uncertainty due to randomness in the environment or policy. Examples: variance across episodes (stochastic transitions, policy sampling), per-episode outcome variability, binomial CI (uncertainty in the observed rate given finite samples).

Both can appear in the same pipeline: e.g. a binomial CI on attack_success_rate is aleatoric (uncertainty in the observed proportion); the detector’s P(attack) is epistemic (model output).

## Metric mapping

The following table maps key metrics and optional fields to uncertainty type. Tools can use the JSON mapping file (see below) for programmatic checks.

| Metric or field | Uncertainty type | Notes |
|-----------------|------------------|--------|
| **confidence** (LLM action_proposal) | Epistemic | Model-reported confidence per decision. |
| **detector probability** (DetectResult.probability) | Epistemic | Model output for P(attack). |
| **Bootstrap CI half-width** (e.g. pareto per-method CI) | Epistemic | Uncertainty in estimated mean/quantile. |
| **ECE, MCE** (detector or LLM calibration) | Epistemic | Calibration error of probability outputs. |
| **llm_confidence_calibration** (ece, mce) | Epistemic | Per-episode ECE/MCE over (confidence, accepted). |
| **\*_std** in summaries | Aleatoric | Standard deviation across episodes. |
| **Episode-level variance** (e.g. throughput variance) | Aleatoric | Variability across runs. |
| **Binomial CI** (containment_success_rate_ci_*, attack_success_rate_ci_*) | Aleatoric | Uncertainty in observed proportion (finite n). |
| **containment_success_rate_ci_lower/upper** | Aleatoric | Clopper–Pearson (or Wilson) for containment rate. |
| **sec.attack_success_rate_ci_lower/upper** | Aleatoric | CI for observed attack success rate. |
| **sec.worst_case_attack_success_upper_95** | Aleatoric | Upper bound when 0 failures observed (rule-of-three style). |

## JSON mapping (optional)

A small mapping file for tools is at **policy/benchmarks/uncertainty_metric_mapping.v0.1.json** (if present). It lists metric keys and their `uncertainty_type` (`epistemic` | `aleatoric`). Tests (e.g. `tests/test_uncertainty_quantification_mapping.py`) assert that every key in the mapping exists in the metrics contract or in v0.3 summary column names, so the doc and mapping stay aligned with the codebase.

## Standard reporting

Uncertainty fields are included in regular benchmark and coordination outputs (no custom export). See [Metrics contract – Uncertainty metrics in standard reports](../contracts/metrics_contract.md#uncertainty-metrics-in-standard-reports) for which outputs contain which columns (summary_v0.3.csv, summary_coord.csv, pack_summary.csv, SECURITY/coordination_risk_matrix).

## Uncertainty report script

**scripts/uncertainty_report.py** (and optional `labtrust uncertainty-report --run <dir>`) loads a run directory's summary CSV and `policy/benchmarks/uncertainty_metric_mapping.v0.1.json`, and outputs a short report with **Epistemic** and **Aleatoric** sections (metrics present in the summary that appear in the mapping). Columns in the summary that are not in the mapping are listed under "Columns not in mapping." Use for evidence review and to ensure mapping coverage.

### Gate (threshold check)

Use `--gate <path>` to pass a YAML file that defines thresholds per metric. The script checks the first row of the summary CSV against these thresholds and exits with code 1 if any are violated. Gate YAML shape:

```yaml
thresholds:
  epistemic:
    llm_confidence_ece_mean: { max: 0.1 }
  aleatoric:
    containment_success_rate_ci_lower: { min: 0.8 }
```

In CI or release, run the report with `--gate` and fail the step on non-zero exit. See metrics_contract for column semantics.

## References

- Rate CIs and worst-case: `src/labtrust_gym/benchmarks/rate_uncertainty.py`
- Detector ECE/MCE: `src/labtrust_gym/baselines/coordination/assurance/detector_advisor.py`
- Pareto bootstrap/robust: `src/labtrust_gym/benchmarks/pareto.py`
- Metrics contract: [Metrics contract](../contracts/metrics_contract.md)
