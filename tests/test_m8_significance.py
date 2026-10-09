"""M8: multiple-testing machinery for the study harness, checked against hand values."""

import pytest

from tennisdb.research.significance import (
    benjamini_hochberg,
    bonferroni,
    two_sided_binomial_p_value,
)

pytestmark = pytest.mark.m8


def test_p_value_observed_equals_expected_is_one():
    assert two_sided_binomial_p_value(successes=50, trials=100, expected_successes=50.0) == (
        pytest.approx(1.0)
    )


def test_p_value_two_standard_errors_out_is_about_five_percent():
    # n=100, p=0.5 -> sd 5; observed 60 is +2 sd (no continuity correction)
    p_value = two_sided_binomial_p_value(successes=60, trials=100, expected_successes=50.0)

    assert p_value == pytest.approx(0.0455, abs=1e-4)


def test_p_value_zero_trials_is_one():
    assert two_sided_binomial_p_value(successes=0, trials=0, expected_successes=0.0) == 1.0


def test_p_value_uses_the_market_expectation_not_one_half():
    # expecting 70 of 100: 70 is perfectly ordinary, 50 is not
    typical = two_sided_binomial_p_value(70, 100, 70.0)
    surprising = two_sided_binomial_p_value(50, 100, 70.0)

    assert typical > 0.9 and surprising < 0.001


def test_bonferroni_scales_by_test_count_and_caps_at_one():
    assert bonferroni([0.01, 0.4, 0.9]) == [pytest.approx(0.03), 1.0, 1.0]


def test_bonferroni_empty_input_returns_empty():
    assert bonferroni([]) == []


def test_benjamini_hochberg_matches_hand_computed_adjustment():
    # sorted p: .01 .02 .03 .04 .50 -> raw adj .05 .05 .05 .05 .50
    adjusted = benjamini_hochberg([0.04, 0.01, 0.50, 0.03, 0.02])

    assert adjusted == [pytest.approx(v) for v in (0.05, 0.05, 0.50, 0.05, 0.05)]


def test_benjamini_hochberg_preserves_input_order_and_is_monotone_in_rank():
    adjusted = benjamini_hochberg([0.9, 0.001, 0.2])

    assert adjusted[1] <= adjusted[2] <= adjusted[0]
    assert all(0.0 <= value <= 1.0 for value in adjusted)


def test_benjamini_hochberg_empty_input_returns_empty():
    assert benjamini_hochberg([]) == []
