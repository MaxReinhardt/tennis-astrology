"""M4: hand-verified matches resolve to their canonical ids on the real warehouse.

Each fixture is a famous match whose winner is a matter of public record, spread
across eras, tours, and every resolution mechanism (exact keys, prefix initials,
multi-initials, hyphen folding, player seeds, edition seeds, tournament synonyms).
"""

import csv
from dataclasses import dataclass

import duckdb
import pytest

from tennisdb.config import DUCKDB_PATH, QUALITY_DIR
from tennisdb.resolve.pipeline import UNMATCHED_FILE

pytestmark = pytest.mark.m4


@dataclass(frozen=True)
class SpotCheck:
    description: str
    tour: str
    season: int
    tournament_like: str
    winner: str
    loser: str
    round: str
    match_id: str


SPOT_CHECKS = (
    SpotCheck("2019 Wimbledon F: Djokovic d. Federer",
              "atp", 2019, "Wimbledon", "Djokovic N.", "Federer R.", "F", "2019-540-226"),
    SpotCheck("2019 Wimbledon F: Halep d. S. Williams (wta edition prefix)",
              "wta", 2019, "Wimbledon", "Halep S.", "Williams S.", "F", "wta-2019-540-226"),
    SpotCheck("2012 Australian Open F: Djokovic d. Nadal",
              "atp", 2012, "Australian Open", "Djokovic N.", "Nadal R.", "F", "2012-580-127"),
    SpotCheck("2013 French Open F: Nadal d. Ferrer (Roland Garros synonym)",
              "atp", 2013, "French Open", "Nadal R.", "Ferrer D.", "F", "2013-520-127"),
    SpotCheck("2021 French Open F: Djokovic d. Tsitsipas",
              "atp", 2021, "French Open", "Djokovic N.", "Tsitsipas S.", "F", "2021-520-226"),
    SpotCheck("2005 US Open F: Federer d. Agassi",
              "atp", 2005, "US Open", "Federer R.", "Agassi A.", "F", "2005-560-127"),
    SpotCheck("2016 Australian Open F: Kerber d. S. Williams",
              "wta", 2016, "Australian Open", "Kerber A.", "Williams S.", "F",
              "wta-2016-580-226"),
    SpotCheck("2007 US Open F: Henin d. Kuznetsova (first WTA odds season)",
              "wta", 2007, "US Open", "Henin J.", "Kuznetsova S.", "F",
              "wta-2007-W-SL-USA-01A-2007-127"),
    SpotCheck("2008 Wimbledon F: V. Williams d. S. Williams (shared surname)",
              "wta", 2008, "Wimbledon", "Williams V.", "Williams S.", "F",
              "wta-2008-W-SL-GBR-01A-2008-127"),
    SpotCheck("2020 Cologne 1 F: Zverev d. Auger-Aliassime (edition seed + hyphen fold)",
              "atp", 2020, "bett1HULKS Indoors", "Zverev A.", "Auger-Aliassime F.", "F",
              "2020-9404-300"),
    SpotCheck("2017 Montreal F: Zverev d. Federer (Canada Masters synonym)",
              "atp", 2017, "Rogers Masters", "Zverev A.", "Federer R.", "F", "2017-0421-300"),
    SpotCheck("2016 US Open SF: Ka. Pliskova d. S. Williams (prefix initial)",
              "wta", 2016, "US Open", "Pliskova Ka.", "Williams S.", "SF", "wta-2016-560-224"),
    SpotCheck("2019 Atlanta F: De Minaur d. Fritz (multi-word last name)",
              "atp", 2019, "%Atlanta%", "De Minaur A.", "Fritz T.", "F", "2019-6116-300"),
    SpotCheck("2009 US Open F: Del Potro d. Federer (multi-initial key)",
              "atp", 2009, "US Open", "Del Potro J.M.", "Federer R.", "F", "2009-560-127"),
    SpotCheck("2016 Auckland F: Bautista Agut d. Sock (player seed alias)",
              "atp", 2016, "ASB Classic", "Bautista R.", "Sock J.", "F", "2016-0301-300"),
    SpotCheck("2019 Tour Finals RR: Zverev d. Nadal (Masters Cup synonym, RR round)",
              "atp", 2019, "Masters Cup", "Zverev A.", "Nadal R.", "RR", "2019-0605-295"),
    SpotCheck("2015 WTA Finals F: Radwanska d. Kvitova (edition seed)",
              "wta", 2015, "Sony Ericsson Championships", "Radwanska A.", "Kvitova P.", "F",
              "wta-2015-W-WT-SIN-01A-2015-15"),
    SpotCheck("2022 Australian Open F: Nadal d. Medvedev",
              "atp", 2022, "Australian Open", "Nadal R.", "Medvedev D.", "F", "2022-580-226"),
    SpotCheck("2018 Washington R32: Pouille d. Millot (retirement)",
              "atp", 2018, "Citi Open", "Pouille L.", "Millot V.", "R32", "2018-M035-273"),
)


@pytest.fixture(scope="module")
def connection():
    if not DUCKDB_PATH.exists():
        pytest.fail(
            "data/warehouse.duckdb missing — run `uv run python scripts/build_db.py "
            "--stage --load --resolve` first"
        )
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield con
    con.close()


@pytest.mark.parametrize("check", SPOT_CHECKS, ids=lambda check: check.description)
def test_fixture_resolves_to_expected_match(connection, check):
    resolved_ids = {
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT o.match_id "
            "FROM staging.tennisdata_matches AS t "
            "JOIN tennis.odds AS o ON o.source_row = t.source_file || ':' || t.source_row "
            "WHERE t.tour = ? AND t.season = ? AND t.Tournament LIKE ? "
            "  AND trim(t.Winner) = ? AND trim(t.Loser) = ? AND t.round = ?",
            [check.tour, check.season, check.tournament_like,
             check.winner, check.loser, check.round],
        ).fetchall()
    }

    assert resolved_ids == {check.match_id}


@pytest.mark.parametrize("check", SPOT_CHECKS, ids=lambda check: check.description)
def test_fixture_has_bet365_odds(connection, check):
    bookmakers = {
        row[0]
        for row in connection.execute(
            "SELECT bookmaker FROM tennis.odds WHERE match_id = ?", [check.match_id]
        ).fetchall()
    }

    assert "B365" in bookmakers


def test_row_with_no_bookmaker_pair_still_resolves():
    """2001 Wimbledon F (Ivanisevic d. Rafter) carries none of the four emitted
    bookmaker pairs, so it appears in neither tennis.odds nor the unmatched CSV —
    match-rate accounting counts it as resolved."""
    path = QUALITY_DIR / UNMATCHED_FILE
    if not path.exists():
        pytest.fail(f"{path} missing — run `uv run python scripts/build_db.py --resolve` first")
    with path.open(newline="", encoding="utf-8") as handle:
        unmatched = [
            row for row in csv.DictReader(handle)
            if row["season"] == "2001" and row["winner"].strip() == "Ivanisevic G."
            and row["round"] == "F"
        ]

    assert unmatched == []
