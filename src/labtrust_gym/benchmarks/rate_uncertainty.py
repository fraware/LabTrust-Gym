"""
Binomial rate uncertainty: Clopper-Pearson CI and worst-case failure rate bound.

Used for safety/security metrics (containment_success, attack_success_rate) to report
confidence intervals and worst-case upper bounds. Optional scipy for exact
Clopper-Pearson; fallback to Wilson score interval when scipy is not available.
"""

from __future__ import annotations

import math

try:
    from scipy.stats import beta as scipy_beta

    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def clopper_pearson_ci(
    successes: int,
    trials: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """
    Clopper-Pearson (exact) confidence interval for the true proportion.

    Returns (lower, upper) for the success rate. When scipy is available uses
    Beta distribution; otherwise falls back to Wilson score interval.

    Edge cases: trials=0 returns (0.0, 0.0); k<0 or k>n clamped to [0,1].
    """
    if trials <= 0:
        return (0.0, 0.0)
    k = max(0, min(successes, trials))
    alpha = 1.0 - confidence
    if alpha <= 0 or alpha >= 1:
        return (0.0, 1.0)
    lo_tail = alpha / 2.0
    hi_tail = 1.0 - alpha / 2.0

    if _HAS_SCIPY:
        # Clopper-Pearson: lower = Beta(k, n-k+1).ppf(alpha/2), upper = Beta(k+1, n-k).ppf(1-alpha/2)
        # For k=0: lower=0, upper = Beta(1,n).ppf(1-alpha/2)
        # For k=n: lower = Beta(n,1).ppf(alpha/2), upper=1
        if k == 0:
            low = 0.0
            high = float(scipy_beta.ppf(hi_tail, 1, trials))
        elif k == trials:
            low = float(scipy_beta.ppf(lo_tail, trials, 1))
            high = 1.0
        else:
            low = float(scipy_beta.ppf(lo_tail, k, trials - k + 1))
            high = float(scipy_beta.ppf(hi_tail, k + 1, trials - k))
        return (max(0.0, min(1.0, low)), max(0.0, min(1.0, high)))

    # Wilson score interval (no scipy); z = approximate norm quantile for 1 - alpha/2
    p = k / trials
    z = 1.96  # 0.95 default
    if confidence >= 0.99:
        z = 2.576
    elif confidence >= 0.95:
        z = 1.96
    elif confidence >= 0.90:
        z = 1.645
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    low = max(0.0, centre - half)
    high = min(1.0, centre + half)
    return (low, high)


def worst_case_failure_rate_upper(
    trials: int,
    confidence: float = 0.95,
) -> float:
    """
    Upper bound on the failure rate when 0 failures were observed in n trials.

    When no failures are observed, the (1 - confidence) one-sided upper bound
    for the failure rate is 1 - (1 - (1-confidence))^(1/n) = 1 - confidence^(1/n).
    E.g. for 95% confidence (confidence=0.95): failure_upper = 1 - 0.95^(1/n).
    Rule-of-three approximation 3/n is close for 95% and moderate n.

    Returns 1.0 if trials <= 0.
    """
    if trials <= 0:
        return 1.0
    # P(0 failures | n trials, true failure rate = p) = (1-p)^n. Set = (1-confidence) => p = 1 - (1-confidence)^(1/n)
    return 1.0 - math.pow(1.0 - confidence, 1.0 / trials)


def worst_case_success_rate_upper(
    trials: int,
    confidence: float = 0.95,
) -> float:
    """
    Upper bound on the success rate when 0 successes were observed in n trials.

    One-sided upper (1 - (1-confidence)) bound: 1 - (1-confidence)^(1/n).
    Used e.g. for sec.worst_case_attack_success_upper_95 when 0 attacks succeeded.
    Returns 0.0 if trials <= 0.
    """
    if trials <= 0:
        return 0.0
    return 1.0 - math.pow(1.0 - confidence, 1.0 / trials)
