"""Rolling pre-match serve form, oriented to the leak-free p1/p2 of matches_model.

tennis.match_stats is sparse — many matches carry no serve line at all — so a
window of "the last N matches" means the last N matches that *recorded* that metric,
never the last N matches played. Every window and delta is placed on a player's
sequence with `shift(1)` then forward-filled, both grouped by player, so a statless
match still carries the player's last known form and a stat-carrying match never sees
its own stats (the as-of guarantee holds by construction; see `_as_of`).

Each metric decides its own "recorded" subsequence independently (a match can carry
some stat columns and not others, and a metric like break-points-saved is routinely
undefined mid-sequence when no break point was faced) — that per-metric masking is
the Strategy `ServeMetric.per_match_value` exists to encapsulate. The two
`serve_matches_available` counters use one shared, coarser mask instead: whether the
match recorded a serve-points line at all.
"""

from dataclasses import dataclass
from typing import Protocol

import duckdb
import pandas as pd

from tennisdb.features.ordering import in_match_order

_LONG_WINDOW = 5
_STAT_COLUMNS = (
    "ace", "df", "svpt", "1stin", "1stwon", "2ndwon", "svgms", "bpsaved", "bpfaced",
)  # fmt: skip


class ServeMetric(Protocol):
    """Strategy: one serve metric's per-match value and its short window length."""

    name: str
    short_window: int

    def per_match_value(self, long: pd.DataFrame) -> pd.Series: ...


@dataclass(frozen=True)
class RateMetric:
    """A metric expressed as numerator / denominator, undefined unless the
    denominator is present and strictly positive."""

    name: str
    numerator: str
    denominator: str
    short_window: int

    def per_match_value(self, long: pd.DataFrame) -> pd.Series:
        numerator = long[self.numerator]
        denominator = long[self.denominator]
        valid = numerator.notna() & denominator.notna() & (denominator > 0)
        return (numerator / denominator).where(valid)


@dataclass(frozen=True)
class CountMetric:
    """A raw per-match count, undefined (not zero) when nothing was recorded."""

    name: str
    column: str
    short_window: int

    def per_match_value(self, long: pd.DataFrame) -> pd.Series:
        count = long[self.column]
        return count.where(count.notna() & (count > 0))


_METRICS: tuple[ServeMetric, ...] = (
    RateMetric("ace_rate", "ace", "svpt", 3),
    RateMetric("df_rate", "df", "svpt", 3),
    RateMetric("first_won_pct", "1stwon", "1stin", 2),
    RateMetric("second_won_pct", "2ndwon", "second_serve_pts", 2),
    RateMetric("bp_saved_pct", "bpsaved", "bpfaced", 2),
    RateMetric("bp_faced_per_game", "bpfaced", "svgms", 2),
    CountMetric("sv_games", "svgms", 2),
)

_MATCHES_QUERY = """
SELECT
  m.match_id,
  m.edition_id,
  m.winner_id,
  m.loser_id,
  coalesce(m.match_date, e.start_date) AS order_date,
  m.round,
  s.w_ace, s.w_df, s.w_svpt, s.w_1stin, s.w_1stwon, s.w_2ndwon,
  s.w_svgms, s.w_bpsaved, s.w_bpfaced,
  s.l_ace, s.l_df, s.l_svpt, s.l_1stin, s.l_1stwon, s.l_2ndwon,
  s.l_svgms, s.l_bpsaved, s.l_bpfaced
FROM tennis.matches AS m
JOIN tennis.tournament_editions AS e USING (edition_id)
LEFT JOIN tennis.match_stats AS s USING (match_id)
"""


def compute_serve_form(matches: pd.DataFrame) -> pd.DataFrame:
    """Pure core: winner/loser-oriented rolling serve-quality features. Depends only
    on the chronological sort, never on the input row order — the as-of guarantee."""
    ordered = in_match_order(matches)
    long = _one_row_per_player(ordered)
    long["second_serve_pts"] = long["svpt"] - long["1stin"]
    long = _add_prior_aggregates(long)
    return _join_both_sides(ordered, long)


def _one_row_per_player(ordered: pd.DataFrame) -> pd.DataFrame:
    sides = [
        pd.DataFrame(
            {
                "match_id": ordered["match_id"],
                "player_id": ordered[f"{role}_id"],
                "order_date": ordered["order_date"],
                "round_ordinal": ordered["round_ordinal"],
                **{
                    stat: pd.to_numeric(ordered[f"{prefix}_{stat}"], errors="coerce")
                    for stat in _STAT_COLUMNS
                },
            }
        )
        for role, prefix in (("winner", "w"), ("loser", "l"))
    ]
    return (
        pd.concat(sides, ignore_index=True)
        .sort_values(["player_id", "order_date", "round_ordinal", "match_id"], kind="mergesort")
        .reset_index(drop=True)
    )


def _as_of(values: pd.Series, player_id: pd.Series) -> pd.Series:
    """The last value known strictly before this row, within this player only.

    Grouping the shift keeps one player's rows from following another's in the
    sequence; grouping the ffill again keeps a statless gap from being bridged by a
    different player's history — collapsing either into an ungrouped call reopens
    exactly that leak.
    """
    prior = values.groupby(player_id, sort=False).shift(1)
    return prior.groupby(player_id, sort=False).ffill()


def _rolling_metric_features(metric: ServeMetric, long: pd.DataFrame) -> dict[str, pd.Series]:
    player_id = long["player_id"]
    value = metric.per_match_value(long)
    observed = value.dropna()
    grouped = observed.groupby(player_id.loc[observed.index], sort=False)

    def _as_of_reindexed(inclusive: pd.Series) -> pd.Series:
        return _as_of(inclusive.reindex(long.index), player_id)

    short = _as_of_reindexed(
        grouped.transform(lambda s: s.rolling(metric.short_window, min_periods=1).mean())
    )
    long_window = _as_of_reindexed(
        grouped.transform(lambda s: s.rolling(_LONG_WINDOW, min_periods=1).mean())
    )
    consecutive = _as_of_reindexed(grouped.transform(lambda s: s.diff()))

    short_name, long_name, consec_name, trend_name = _metric_feature_names(metric)
    return {
        short_name: short,
        long_name: long_window,
        consec_name: consecutive,
        trend_name: short - long_window,
    }


def _availability(long: pd.DataFrame) -> pd.Series:
    player_id = long["player_id"]
    has_serve_line = long["svpt"].notna() & (long["svpt"] > 0)
    recorded = player_id[has_serve_line]
    counted = recorded.groupby(recorded, sort=False).cumcount() + 1
    prior = _as_of(counted.reindex(long.index), player_id)
    return prior.fillna(0).astype("Int64")


def _add_prior_aggregates(long: pd.DataFrame) -> pd.DataFrame:
    features: dict[str, pd.Series] = {}
    for metric in _METRICS:
        features.update(_rolling_metric_features(metric, long))
    features["serve_matches_available"] = _availability(long)
    return long.assign(**features)


def _join_both_sides(ordered: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    names = _bare_feature_names()
    columns = ["match_id", "player_id", *names]
    base = ["match_id", "winner_id", "loser_id"]
    per_match = ordered[base].copy()
    for role, prefix in (("winner", "w"), ("loser", "l")):
        side = long[columns].rename(
            columns={"player_id": f"{role}_id", **{name: f"{prefix}_{name}" for name in names}}
        )
        per_match = per_match.merge(side, on=["match_id", f"{role}_id"], how="left")
    for prefix in ("w", "l"):
        per_match[f"{prefix}_serve_matches_available"] = per_match[
            f"{prefix}_serve_matches_available"
        ].astype("Int64")
    return per_match


def _metric_feature_names(metric: ServeMetric) -> tuple[str, str, str, str]:
    return (
        f"{metric.name}_{metric.short_window}",
        f"{metric.name}_{_LONG_WINDOW}",
        f"{metric.name}_delta_consec",
        f"{metric.name}_delta_trend",
    )


def _bare_feature_names() -> tuple[str, ...]:
    names = [name for metric in _METRICS for name in _metric_feature_names(metric)]
    names.append("serve_matches_available")
    return tuple(names)


def feature_columns() -> tuple[str, ...]:
    """Ordered p1/p2-oriented feature columns (excluding match_id) — matches
    db/migrations/006_serve_form.sql and publish.py's SERVE_FORM column tuple."""
    columns = ["p1_serve_matches_available", "p2_serve_matches_available"]
    for metric in _METRICS:
        for prefix in ("p1", "p2"):
            columns.extend(f"{prefix}_{name}" for name in _metric_feature_names(metric))
    return tuple(columns)


SERVE_FORM_COLUMNS = feature_columns()

# Metrics whose per-match value is mathematically confined to [0, 1] (aces, double
# faults, and points won are each a subset of the serve points they're divided by).
# bp_faced_per_game and sv_games are excluded — a service game can contain more than
# one break point, and games played has no such ceiling.
_BOUNDED_RATE_METRIC_NAMES = frozenset(
    {"ace_rate", "df_rate", "first_won_pct", "second_won_pct", "bp_saved_pct"}
)


def bounded_rate_columns() -> tuple[str, ...]:
    """p1/p2 window-average columns guaranteed to fall in [0, 1] — used by the
    quality suite to catch a broken formula or a p1/p2 alignment bug. Deltas are
    excluded: a difference of two [0, 1] values ranges over [-1, 1], not [0, 1]."""
    return tuple(
        f"{prefix}_{metric.name}_{window}"
        for metric in _METRICS
        if metric.name in _BOUNDED_RATE_METRIC_NAMES
        for window in (metric.short_window, _LONG_WINDOW)
        for prefix in ("p1", "p2")
    )


BOUNDED_RATE_COLUMNS = bounded_rate_columns()


def _orient_expression(column: str) -> str:
    prefix, rest = column.split("_", 1)
    own, other = ("w", "l") if prefix == "p1" else ("l", "w")
    return f"CASE WHEN m.p1_won THEN f.{own}_{rest} ELSE f.{other}_{rest} END"


def _build_orient_and_insert_sql() -> str:
    selected = ["f.match_id"] + [_orient_expression(column) for column in SERVE_FORM_COLUMNS]
    select_clause = ",\n  ".join(selected)
    return (
        "INSERT INTO analytics.serve_form\n"
        f"SELECT\n  {select_clause}\n"
        "FROM _serve_form_rows AS f\n"
        "JOIN tennis.matches_model AS m USING (match_id)\n"
    )


_ORIENT_AND_INSERT = _build_orient_and_insert_sql()


def build_serve_form(connection: duckdb.DuckDBPyConnection) -> int:
    matches = connection.execute(_MATCHES_QUERY).fetch_df()
    per_match = compute_serve_form(matches)
    connection.execute("DELETE FROM analytics.serve_form")
    connection.register("_serve_form_rows", per_match)
    try:
        return connection.execute(_ORIENT_AND_INSERT).fetchone()[0]
    finally:
        connection.unregister("_serve_form_rows")
