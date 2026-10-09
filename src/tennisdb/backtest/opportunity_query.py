"""The one opportunity query both OpportunitySource adapters run (DuckDB locally,
Postgres/Supabase when serving). Written in the DuckDB/Postgres common SQL subset, like
db/migrations; the only dialect difference is the bind-placeholder token, which callers
pass in. Every filter is pushed down to SQL so Python only iterates the matches the
request wants, in features.ordering.in_match_order's chronological order.

Host nationality is joined with LEFT JOINs on purpose: an unknown host or nationality
must make a match "not home", never drop it from the universe.
"""

from collections.abc import Iterable, Iterator, Mapping

from tennisdb.backtest.domain import MatchEvent, MatchOpportunity
from tennisdb.backtest.request import BacktestRequest
from tennisdb.features.elo import elo_probability
from tennisdb.features.ordering import DEFAULT_ROUND_ORDINAL, ROUND_ORDINAL

DUCKDB_PLACEHOLDER = "?"
POSTGRES_PLACEHOLDER = "%s"

_ROUND_CASE = "CASE model.round {whens} ELSE {default} END".format(
    whens=" ".join(f"WHEN '{name}' THEN {ordinal}" for name, ordinal in ROUND_ORDINAL.items()),
    default=DEFAULT_ROUND_ORDINAL,
)

_QUERY_TEMPLATE = """
WITH fill AS (
  SELECT
    match_id,
    CAST(winner_odds AS DOUBLE PRECISION) AS winner_price,
    CAST(loser_odds AS DOUBLE PRECISION) AS loser_price,
    row_number() OVER (PARTITION BY match_id ORDER BY {fill_preference_case}) AS preference
  FROM tennis.odds
  WHERE bookmaker IN ({fill_book_placeholders})
    AND winner_odds IS NOT NULL AND loser_odds IS NOT NULL
)
SELECT
  model.match_id,
  coalesce(model.match_date, e.start_date) AS match_date,
  e.season,
  e.tour,
  e.surface,
  e.level,
  model.round,
  model.p1_won,
  CASE WHEN model.p1_won THEN fill.winner_price ELSE fill.loser_price END AS p1_price,
  CASE WHEN model.p1_won THEN fill.loser_price ELSE fill.winner_price END AS p2_price,
  CAST(CASE WHEN model.p1_won THEN consensus.winner_odds ELSE consensus.loser_odds END
    AS DOUBLE PRECISION) AS p1_consensus_price,
  CAST(CASE WHEN model.p1_won THEN consensus.loser_odds ELSE consensus.winner_odds END
    AS DOUBLE PRECISION) AS p2_consensus_price,
  mk.p1_market_prob AS p1_consensus_prob,
  elo.p1_elo_pre, elo.p2_elo_pre,
  elo.p1_surface_elo_pre, elo.p2_surface_elo_pre,
  coalesce(p1.country_ioc = geo.host_country_ioc, false) AS p1_is_home,
  coalesce(p2.country_ioc = geo.host_country_ioc, false) AS p2_is_home
FROM tennis.matches_model AS model
JOIN tennis.tournament_editions AS e ON e.edition_id = model.edition_id
JOIN fill ON fill.match_id = model.match_id
JOIN analytics.market AS mk ON mk.match_id = model.match_id
JOIN analytics.elo_pre AS elo ON elo.match_id = model.match_id
JOIN tennis.odds AS consensus
  ON consensus.match_id = model.match_id AND consensus.bookmaker = mk.bookmaker
LEFT JOIN tennis.players AS p1 ON p1.player_id = model.p1_id
LEFT JOIN tennis.players AS p2 ON p2.player_id = model.p2_id
LEFT JOIN analytics.edition_geo AS geo ON geo.edition_id = model.edition_id
WHERE fill.preference = 1
{filter_clause}
ORDER BY match_date, model.edition_id, {round_case}, model.match_id
"""


def build_query(request: BacktestRequest, placeholder: str) -> tuple[str, list]:
    filter_clause, filter_params = _filter_clause(request, placeholder)
    fill_books = request.fill_preference
    query = _QUERY_TEMPLATE.format(
        fill_preference_case=_fill_preference_case(fill_books),
        fill_book_placeholders=", ".join(placeholder for _ in fill_books),
        filter_clause=filter_clause,
        round_case=_ROUND_CASE,
    )
    return query, [*fill_books, *filter_params]


def events_from_rows(rows: Iterable[Mapping]) -> Iterator[MatchEvent]:
    for row in rows:
        opportunity = MatchOpportunity(
            match_id=row["match_id"],
            match_date=row["match_date"],
            season=int(row["season"]),
            tour=row["tour"],
            surface=row["surface"],
            level=row["level"],
            round=row["round"],
            p1_price=float(row["p1_price"]),
            p2_price=float(row["p2_price"]),
            p1_consensus_price=float(row["p1_consensus_price"]),
            p2_consensus_price=float(row["p2_consensus_price"]),
            p1_consensus_prob=float(row["p1_consensus_prob"]),
            p1_elo_prob=elo_probability(row["p1_elo_pre"], row["p2_elo_pre"]),
            p1_surface_elo_prob=elo_probability(
                row["p1_surface_elo_pre"], row["p2_surface_elo_pre"]
            ),
            p1_is_home=bool(row["p1_is_home"]),
            p2_is_home=bool(row["p2_is_home"]),
        )
        yield MatchEvent(opportunity=opportunity, p1_won=bool(row["p1_won"]))


def _fill_preference_case(fill_preference: tuple[str, ...]) -> str:
    whens = " ".join(f"WHEN '{book}' THEN {rank}" for rank, book in enumerate(fill_preference))
    return f"CASE bookmaker {whens} ELSE {len(fill_preference)} END"


def _filter_clause(request: BacktestRequest, placeholder: str) -> tuple[str, list]:
    filters = request.filters
    conditions: list[tuple[str, list]] = []
    if filters.tour is not None:
        conditions.append(("e.tour = {}", [filters.tour]))
    for column, values in (
        ("e.surface", filters.surfaces),
        ("e.level", filters.levels),
        ("model.round", filters.rounds),
    ):
        if values:
            conditions.append((f"{column} IN ({', '.join('{}' for _ in values)})", list(values)))
    if filters.from_season is not None:
        conditions.append(("e.season >= {}", [filters.from_season]))
    if filters.to_season is not None:
        conditions.append(("e.season <= {}", [filters.to_season]))
    clause = "".join(
        f"  AND {template.format(*([placeholder] * len(values)))}\n"
        for template, values in conditions
    )
    params = [value for _, values in conditions for value in values]
    return clause, params
