"""DuckDB implementation of MatchCrossSection. Each match yields two observations (one
per player) carrying that player's no-vig market win probability, so any cohort can be
tested against what the market already priced in. Dimensions are a registry of SQL
fragments (Strategy over a switch): adding one is one entry."""

from dataclasses import dataclass

import duckdb

from tennisdb.research.context import GroupOutcome

# DuckDB sums in parallel, so the float result varies in its last bits between runs;
# rounding far above that noise keeps study results byte-reproducible.
_EXPECTATION_DECIMALS = 6


@dataclass(frozen=True)
class Dimension:
    group_expression: str
    joins: str = ""
    condition: str = "TRUE"


_ASTRO_JOIN = "JOIN analytics.player_astro AS astro ON astro.player_id = obs.player_id"

DIMENSIONS: dict[str, Dimension] = {
    "zodiac_sign": Dimension("astro.zodiac_sign", _ASTRO_JOIN, "astro.zodiac_sign IS NOT NULL"),
    "zodiac_element": Dimension("astro.element", _ASTRO_JOIN, "astro.element IS NOT NULL"),
    "birth_month": Dimension(
        "CAST(astro.birth_month AS VARCHAR)", _ASTRO_JOIN, "astro.birth_month IS NOT NULL"
    ),
    "host_nation": Dimension(
        "CASE WHEN obs.player_country = obs.host_country THEN 'home' ELSE 'visitor' END",
        condition=(
            "obs.host_country IS NOT NULL AND obs.player_country IS NOT NULL "
            "AND obs.opponent_country IS NOT NULL "
            "AND (obs.player_country = obs.host_country) "
            "<> (obs.opponent_country = obs.host_country)"
        ),
    ),
}

_OBSERVATIONS = """
WITH sided AS (
  SELECT model.match_id, model.p1_id AS player_id, model.p2_id AS opponent_id,
         model.edition_id, model.p1_won AS won, market.p1_market_prob AS expected
  FROM tennis.matches_model AS model
  JOIN analytics.market AS market ON market.match_id = model.match_id
  UNION ALL
  SELECT model.match_id, model.p2_id, model.p1_id, model.edition_id,
         NOT model.p1_won, market.p2_market_prob
  FROM tennis.matches_model AS model
  JOIN analytics.market AS market ON market.match_id = model.match_id
),
obs AS (
  SELECT sided.*, player.country_ioc AS player_country, opponent.country_ioc AS opponent_country,
         geo.host_country_ioc AS host_country
  FROM sided
  LEFT JOIN tennis.players AS player ON player.player_id = sided.player_id
  LEFT JOIN tennis.players AS opponent ON opponent.player_id = sided.opponent_id
  LEFT JOIN analytics.edition_geo AS geo ON geo.edition_id = sided.edition_id
)
SELECT {group_expression} AS grp, count(*), sum(CASE WHEN obs.won THEN 1 ELSE 0 END),
       sum(obs.expected)
FROM obs {joins}
WHERE {condition}
GROUP BY 1
ORDER BY 1
"""


class DuckDbCrossSection:
    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self._connection = connection

    def outcomes(self, dimension: str) -> list[GroupOutcome]:
        spec = DIMENSIONS[dimension]
        query = _OBSERVATIONS.format(
            group_expression=spec.group_expression, joins=spec.joins, condition=spec.condition
        )
        return [
            GroupOutcome(
                group, int(trials), int(successes), round(float(expected), _EXPECTATION_DECIMALS)
            )
            for group, trials, successes, expected in self._connection.execute(query).fetchall()
        ]
