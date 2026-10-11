"""M8: study verdict logic against fake contexts — no database, fully deterministic."""

from datetime import date

import pytest

from tennisdb.backtest.domain import SettledBet
from tennisdb.backtest.report import build_result
from tennisdb.research.context import GroupOutcome, StudyContext
from tennisdb.research.protocol import Verdict
from tennisdb.research.studies import STUDIES
from tennisdb.research.studies.s1_clv_persistence import _verdict as clv_verdict
from tennisdb.research.studies.s2_favourite_longshot import _verdict as bias_verdict

pytestmark = pytest.mark.m8


def _bets(count, win_fraction, price=2.0, consensus=2.0):
    wins = int(count * win_fraction)
    return [
        SettledBet(
            match_id=f"m{index}", match_date=date(2019, 1, 1 + index % 28), side="p1",
            probability=0.5, price=price, fill_price=price, consensus_price=consensus,
            consensus_prob=1 / consensus, stake=10.0,
            profit=10.0 * (price - 1) if index < wins else -10.0, won=index < wins,
            bankroll_after=1_000_000.0, surface="Hard",
        )
        for index in range(count)
    ]  # fmt: skip


class _FakeRunner:
    def __init__(self, count, win_fraction):
        self._bets = _bets(count, win_fraction)

    def run(self, request):
        return build_result(request, len(self._bets), list(self._bets))


class _FakeCrossSection:
    def __init__(self, outcomes_by_dimension):
        self._outcomes = outcomes_by_dimension

    def outcomes(self, dimension):
        return self._outcomes.get(dimension, [])


def _market_matched(group, trials=10_000):
    return GroupOutcome(group, trials, trials // 2, trials / 2)


def _context(count=2000, win_fraction=0.5, outcomes=None):
    return StudyContext(_FakeRunner(count, win_fraction), _FakeCrossSection(outcomes or {}))


def test_every_registered_study_has_a_complete_preregistration():
    for study_id, study in STUDIES.items():
        hypothesis = study.hypothesis
        assert study.study_id == study_id
        assert all(vars(hypothesis).values()), study_id


def test_zodiac_study_cohorts_matching_the_market_is_not_supported():
    outcomes = {"zodiac_sign": [_market_matched(f"sign{i}") for i in range(12)]}

    result = STUDIES["s3_zodiac_null"].run(_context(outcomes=outcomes))

    assert result.verdict is Verdict.NOT_SUPPORTED


def test_zodiac_study_survives_correction_only_for_a_large_real_deviation():
    cohorts = [_market_matched(f"sign{i}") for i in range(11)]
    cohorts.append(GroupOutcome("rigged", 20_000, 12_000, 10_000.0))

    result = STUDIES["s3_zodiac_null"].run(_context(outcomes={"zodiac_sign": cohorts}))

    assert result.verdict is Verdict.SUPPORTED


def test_zodiac_study_reports_correction_that_never_decreases_a_p_value():
    outcomes = {"zodiac_sign": [GroupOutcome("a", 1000, 540, 500.0), _market_matched("b")]}

    table = STUDIES["s3_zodiac_null"].run(_context(outcomes=outcomes)).tables[0]

    assert all(float(row[6]) >= float(row[5]) for row in table.rows)


def test_host_nation_study_no_gap_and_no_profit_is_not_supported():
    outcomes = {"host_nation": [_market_matched("home"), _market_matched("visitor")]}

    result = STUDIES["s4_host_nation"].run(_context(win_fraction=0.4, outcomes=outcomes))

    assert result.verdict is Verdict.NOT_SUPPORTED


def test_host_nation_study_reports_both_strategies_on_both_samples_and_a_control():
    outcomes = {"host_nation": [_market_matched("home")]}

    result = STUDIES["s4_host_nation"].run(_context(outcomes=outcomes))

    assert len(result.tables[1].rows) == 5


def test_clv_study_too_few_tuning_bets_is_inconclusive():
    result = STUDIES["s1_clv_persistence"].run(_context(count=50))

    assert result.verdict is Verdict.INCONCLUSIVE


@pytest.mark.parametrize(
    ("clv_low", "control_clv", "roi_low", "roi_high", "expected"),
    [
        (0.03, 0.01, -0.05, 0.04, Verdict.SUPPORTED),
        (0.02, 0.028, -0.05, 0.04, Verdict.NOT_SUPPORTED),
        (0.03, 0.01, -0.12, -0.04, Verdict.INCONCLUSIVE),
    ],
)
def test_clv_verdict_reads_clv_against_the_control_and_the_roi_interval(
    clv_low, control_clv, roi_low, roi_high, expected
):
    assert clv_verdict(clv_low, control_clv, roi_low, roi_high)[0] is expected


def test_favourite_longshot_verdict_a_profitable_bucket_is_not_supported():
    assert bias_verdict({"Hard": True}, ["Hard 10.0+"])[0] is Verdict.NOT_SUPPORTED


def test_favourite_longshot_verdict_bias_everywhere_and_no_profit_is_supported():
    assert bias_verdict({"Hard": True, "Clay": True}, [])[0] is Verdict.SUPPORTED


def test_favourite_longshot_verdict_bias_on_some_surfaces_only_is_inconclusive():
    assert bias_verdict({"Hard": True, "Clay": False}, [])[0] is Verdict.INCONCLUSIVE


def test_study_result_serialises_to_json_ready_dict():
    outcomes = {"host_nation": [_market_matched("home")]}

    payload = STUDIES["s4_host_nation"].run(_context(outcomes=outcomes)).to_dict()

    assert payload["verdict"] in {"supported", "not_supported", "inconclusive"}
    assert payload["tables"] and payload["charts"]


def test_every_registered_study_has_a_plain_language_title_and_summary():
    for study_id, study in STUDIES.items():
        assert study.plain.title.strip(), study_id
        assert study.plain.summary.strip(), study_id


def test_study_result_dict_carries_the_plain_title_and_summary():
    outcomes = {"host_nation": [_market_matched("home")]}
    study = STUDIES["s4_host_nation"]

    payload = study.run(_context(outcomes=outcomes)).to_dict()

    assert payload["plain_title"] == study.plain.title
    assert payload["plain_summary"] == study.plain.summary


def test_results_block_opens_with_the_plain_summary(tmp_path):
    from tennisdb.research.documents import render_results_block

    study = STUDIES["s4_host_nation"]
    result = study.run(_context(outcomes={"host_nation": [_market_matched("home")]}))

    block = render_results_block(result, charts_directory=None)

    assert f"> **In plain words:** {study.plain.summary}" in block


def test_study_index_entry_carries_the_plain_title_and_summary(tmp_path):
    from tennisdb.research.artifacts import write_study_artifacts

    study = STUDIES["s4_host_nation"]
    result = study.run(_context(outcomes={"host_nation": [_market_matched("home")]}))

    write_study_artifacts(
        study, result, studies_directory=tmp_path, with_plots=False,
        api_directory=tmp_path / "api",
    )  # fmt: skip

    import json

    entry = json.loads((tmp_path / "results" / "index.json").read_text())[0]
    assert entry["plain_title"] == study.plain.title
    assert entry["plain_summary"] == study.plain.summary


def test_scaffolded_preregistration_does_not_include_the_plain_layer():
    from tennisdb.research.documents import scaffold_document

    study = STUDIES["s4_host_nation"]

    assert study.plain.summary not in scaffold_document(study)
