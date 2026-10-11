"""Significance tests and multiple-testing corrections for the study harness. Pure
functions on plain floats, built on math.erfc so no statistics dependency is needed."""

from collections.abc import Sequence
from math import erfc, sqrt


def two_sided_binomial_p_value(successes: int, trials: int, expected_successes: float) -> float:
    """Normal-approximation z-test of `successes` against a market-implied expectation.
    Each trial is a Bernoulli with its own market probability, so the variance is
    approximated with the cohort's mean probability — adequate at the cohort sizes the
    studies use (hundreds of matches and up)."""
    if trials == 0:
        return 1.0
    probability = expected_successes / trials
    variance = trials * probability * (1.0 - probability)
    if variance <= 0.0:
        return 1.0 if successes == expected_successes else 0.0
    z_score = (successes - expected_successes) / sqrt(variance)
    return erfc(abs(z_score) / sqrt(2.0))


def bonferroni(p_values: Sequence[float]) -> list[float]:
    count = len(p_values)
    return [min(1.0, p_value * count) for p_value in p_values]


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """Benjamini–Hochberg false-discovery-rate adjusted p-values, in input order."""
    count = len(p_values)
    ranked = sorted(range(count), key=lambda index: p_values[index])
    adjusted = [0.0] * count
    running_minimum = 1.0
    for rank in range(count, 0, -1):
        index = ranked[rank - 1]
        running_minimum = min(running_minimum, p_values[index] * count / rank)
        adjusted[index] = running_minimum
    return adjusted
