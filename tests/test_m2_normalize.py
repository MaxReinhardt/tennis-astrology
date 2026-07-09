"""M2: pure value normalizers shared by the staging loaders."""

from datetime import date

import pandas as pd
import pytest

from tennisdb.ingest.normalize import (
    CANONICAL_ROUNDS,
    TENNISDATA_FIXED_ROUNDS,
    normalize_odds,
    normalize_sackmann_round,
    normalize_series,
    normalize_surface,
    numbered_round_codes,
    parse_yyyymmdd,
)

pytestmark = pytest.mark.m2


def test_parse_yyyymmdd_valid_date_returns_date():
    assert parse_yyyymmdd("19870822") == date(1987, 8, 22)


def test_parse_yyyymmdd_nineteenth_century_date_returns_date():
    assert parse_yyyymmdd("18991231") == date(1899, 12, 31)


def test_parse_yyyymmdd_partial_dob_returns_none():
    assert parse_yyyymmdd("19750000") is None


def test_parse_yyyymmdd_seven_digit_value_returns_none():
    assert parse_yyyymmdd("2002107") is None


def test_parse_yyyymmdd_impossible_calendar_day_returns_none():
    assert parse_yyyymmdd("20250230") is None


def test_parse_yyyymmdd_missing_value_returns_none():
    assert parse_yyyymmdd(None) is None
    assert parse_yyyymmdd(float("nan")) is None


def test_normalize_odds_float_within_range_passes_through():
    assert normalize_odds(2.35) == 2.35


def test_normalize_odds_numeric_string_parses():
    assert normalize_odds("3.5") == 3.5


def test_normalize_odds_comma_decimal_string_repaired():
    assert normalize_odds("2,25") == 2.25


def test_normalize_odds_zero_returns_none():
    assert normalize_odds(0) is None
    assert normalize_odds("0") is None


def test_normalize_odds_sub_even_money_price_returns_none():
    assert normalize_odds(0.967) is None
    assert normalize_odds(1.0) is None


def test_normalize_odds_minimum_valid_price_accepted():
    assert normalize_odds(1.001) == 1.001


def test_normalize_odds_upper_boundary_excluded():
    assert normalize_odds(1000.99) == 1000.99
    assert normalize_odds(1001) is None


def test_normalize_odds_excel_serial_leakage_returns_none():
    assert normalize_odds(42136.0) is None


def test_normalize_odds_garbage_strings_return_none():
    for garbage in ("5..5", "2.,3", "-", " ", "x`2.51", "1,2,3"):
        assert normalize_odds(garbage) is None, garbage


def test_normalize_odds_missing_value_returns_none():
    assert normalize_odds(None) is None
    assert normalize_odds(float("nan")) is None


def test_normalize_surface_canonical_value_passes_through():
    assert normalize_surface("Hard") == "Hard"


def test_normalize_surface_lowercase_value_folded():
    assert normalize_surface("clay") == "Clay"


def test_normalize_surface_greenset_maps_to_hard():
    assert normalize_surface("Greenset") == "Hard"


def test_normalize_surface_blank_or_unknown_returns_none():
    assert normalize_surface("") is None
    assert normalize_surface(None) is None
    assert normalize_surface("Moon Dust") is None


def test_normalize_sackmann_round_canonical_code_passes_through():
    for code in CANONICAL_ROUNDS:
        assert normalize_sackmann_round(code) == code


def test_normalize_sackmann_round_unknown_code_returns_none():
    assert normalize_sackmann_round("ER") is None
    assert normalize_sackmann_round(None) is None


def test_tennisdata_fixed_rounds_cover_non_numbered_labels():
    assert TENNISDATA_FIXED_ROUNDS == {
        "The Final": "F",
        "Semifinals": "SF",
        "Quarterfinals": "QF",
        "Round Robin": "RR",
        "Third Place": "BR",
    }


def test_numbered_round_codes_deepest_four_maps_first_to_r128():
    assert numbered_round_codes(4) == {
        "1st Round": "R128",
        "2nd Round": "R64",
        "3rd Round": "R32",
        "4th Round": "R16",
    }


def test_numbered_round_codes_deepest_one_maps_first_to_r16():
    assert numbered_round_codes(1) == {"1st Round": "R16"}


def test_numbered_round_codes_deepest_two_maps_first_to_r32():
    assert numbered_round_codes(2) == {"1st Round": "R32", "2nd Round": "R16"}


def test_numbered_round_codes_beyond_canonical_enum_omitted():
    codes = numbered_round_codes(5)
    assert "1st Round" not in codes
    assert codes["2nd Round"] == "R128"


def test_normalize_series_applies_normalizer_and_keeps_nulls():
    series = pd.Series(["2,25", "0", None, "4.2"])

    normalized = normalize_series(series, normalize_odds)

    assert normalized[0] == 2.25
    assert pd.isna(normalized[1])
    assert pd.isna(normalized[2])
    assert normalized[3] == 4.2
