"""Resolve each tennis-data row to its canonical match.

A row joins on (edition, unordered player pair). Orientation must agree — the
sources disagreeing on the winner means a bad join, never a data fact. Round is
a disambiguator, not a filter (M2's inferred rounds can drift from Sackmann's),
then rank proximity breaks remaining ties. Any match claimed by more than one
row demotes all claimants to `ambiguous`, guaranteeing a one-to-one mapping.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

import duckdb

from tennisdb.resolve.players import PlayerAliasMap
from tennisdb.resolve.tournaments import WINDOW_AFTER, WINDOW_BEFORE, EditionAliasMap

MISSING_RANK_PENALTY = 10_000

_ROWS_SQL = """
    SELECT tour, season, Tournament, Location, "Date", round, Winner, Loser,
           WRank, LRank, B365W, B365L, PSW, PSL, MaxW, MaxL, AvgW, AvgL,
           source_file, source_row
    FROM staging.tennisdata_matches
"""

_MATCH_INDEX_SQL = """
    SELECT m.edition_id, m.match_id, m.round, m.winner_id, m.loser_id,
           m.winner_rank, m.loser_rank, e.start_date
    FROM tennis.matches AS m
    JOIN tennis.tournament_editions AS e USING (edition_id)
"""


@dataclass(frozen=True)
class OddsSourceRow:
    tour: str
    season: int
    tournament: str
    location: str
    match_date: date | None
    round: str | None
    winner: str
    loser: str
    winner_rank: int | None
    loser_rank: int | None
    bookmaker_odds: dict[str, tuple[float | None, float | None]]
    source_file: str
    source_row: int


@dataclass(frozen=True)
class CanonicalMatch:
    match_id: str
    round: str
    winner_id: int
    loser_id: int
    winner_rank: int | None
    loser_rank: int | None
    start_date: date | None


@dataclass
class MatchResolution:
    resolved: list[tuple[OddsSourceRow, str]]
    unmatched: list[tuple[OddsSourceRow, str]]

    def reason_counts(self) -> dict[str, int]:
        return dict(Counter(reason for _, reason in self.unmatched))

    def season_tour_counts(self) -> dict[tuple[int, str], tuple[int, int]]:
        matched = Counter((row.season, row.tour) for row, _ in self.resolved)
        totals = matched + Counter((row.season, row.tour) for row, _ in self.unmatched)
        return {key: (matched[key], total) for key, total in totals.items()}


def resolve_matches(
    connection: duckdb.DuckDBPyConnection,
    players: PlayerAliasMap,
    editions: EditionAliasMap,
) -> MatchResolution:
    match_index = _build_match_index(connection)
    claims: list[tuple[OddsSourceRow, str]] = []
    unmatched: list[tuple[OddsSourceRow, str]] = []
    for row in _source_rows(connection):
        match_id, reason = _resolve_row(row, players, editions, match_index)
        if match_id:
            claims.append((row, match_id))
        else:
            unmatched.append((row, reason))
    resolved = _demote_duplicate_claims(claims, unmatched)
    return MatchResolution(resolved, unmatched)


def _resolve_row(
    row: OddsSourceRow,
    players: PlayerAliasMap,
    editions: EditionAliasMap,
    match_index: dict[tuple[str, frozenset[int]], list[CanonicalMatch]],
) -> tuple[str | None, str | None]:
    edition_id = editions.lookup(row.tour, row.season, row.tournament, row.location)
    if edition_id is None:
        return None, "edition_unresolved"
    winner_ids = players.lookup(row.tour, row.winner)
    loser_ids = players.lookup(row.tour, row.loser)
    if not winner_ids or not loser_ids:
        return None, "player_unresolved"
    candidates = _pair_candidates(match_index, edition_id, winner_ids, loser_ids)
    if not candidates:
        return None, "no_candidate"
    if not _within_edition_window(row.match_date, candidates[0].start_date):
        return None, "no_candidate"
    oriented = [
        match
        for match in candidates
        if match.winner_id in winner_ids and match.loser_id in loser_ids
    ]
    if not oriented:
        return None, "winner_mismatch"
    if len(oriented) > 1:
        oriented = [match for match in oriented if match.round == row.round] or oriented
    if len(oriented) > 1:
        oriented = _rank_proximity_winner(oriented, row) or oriented
    if len(oriented) != 1:
        return None, "ambiguous"
    return oriented[0].match_id, None


def _pair_candidates(
    match_index: dict[tuple[str, frozenset[int]], list[CanonicalMatch]],
    edition_id: str,
    winner_ids: frozenset[int],
    loser_ids: frozenset[int],
) -> list[CanonicalMatch]:
    pairs = {
        frozenset((winner, loser))
        for winner in winner_ids
        for loser in loser_ids
        if winner != loser
    }
    return [match for pair in pairs for match in match_index.get((edition_id, pair), [])]


def _within_edition_window(match_date: date | None, start_date: date | None) -> bool:
    if match_date is None or start_date is None:
        return True
    return start_date - WINDOW_BEFORE <= match_date <= start_date + WINDOW_AFTER


def _rank_proximity_winner(
    candidates: list[CanonicalMatch], row: OddsSourceRow
) -> list[CanonicalMatch]:
    penalties = sorted(
        (_rank_distance(row.winner_rank, match.winner_rank)
         + _rank_distance(row.loser_rank, match.loser_rank), index)
        for index, match in enumerate(candidates)
    )
    best_penalty, best_index = penalties[0]
    if penalties[1][0] > best_penalty:
        return [candidates[best_index]]
    return []


def _rank_distance(source_rank: int | None, canonical_rank: int | None) -> int:
    if source_rank is None or canonical_rank is None:
        return MISSING_RANK_PENALTY
    return abs(source_rank - canonical_rank)


def _demote_duplicate_claims(
    claims: list[tuple[OddsSourceRow, str]],
    unmatched: list[tuple[OddsSourceRow, str]],
) -> list[tuple[OddsSourceRow, str]]:
    rows_by_match: dict[str, list[OddsSourceRow]] = defaultdict(list)
    for row, match_id in claims:
        rows_by_match[match_id].append(row)
    resolved = []
    for row, match_id in claims:
        if len(rows_by_match[match_id]) == 1:
            resolved.append((row, match_id))
        else:
            unmatched.append((row, "ambiguous"))
    return resolved


def _build_match_index(
    connection: duckdb.DuckDBPyConnection,
) -> dict[tuple[str, frozenset[int]], list[CanonicalMatch]]:
    index: dict[tuple[str, frozenset[int]], list[CanonicalMatch]] = defaultdict(list)
    for edition_id, match_id, round_, winner_id, loser_id, winner_rank, loser_rank, start_date in (
        connection.execute(_MATCH_INDEX_SQL).fetchall()
    ):
        match = CanonicalMatch(
            match_id, round_, winner_id, loser_id, winner_rank, loser_rank, start_date
        )
        index[(edition_id, frozenset((winner_id, loser_id)))].append(match)
    return index


def _source_rows(connection: duckdb.DuckDBPyConnection) -> list[OddsSourceRow]:
    rows = []
    for (tour, season, tournament, location, match_date, round_, winner, loser, winner_rank,
         loser_rank, b365_w, b365_l, ps_w, ps_l, max_w, max_l, avg_w, avg_l,
         source_file, source_row) in connection.execute(_ROWS_SQL).fetchall():
        rows.append(
            OddsSourceRow(
                tour=tour,
                season=int(season),
                tournament=tournament,
                location=location,
                match_date=match_date,
                round=round_,
                winner=winner,
                loser=loser,
                winner_rank=None if winner_rank is None else int(winner_rank),
                loser_rank=None if loser_rank is None else int(loser_rank),
                bookmaker_odds={
                    "B365": (b365_w, b365_l),
                    "PS": (ps_w, ps_l),
                    "Max": (max_w, max_l),
                    "Avg": (avg_w, avg_l),
                },
                source_file=source_file,
                source_row=int(source_row),
            )
        )
    return rows
