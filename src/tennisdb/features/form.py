"""Rolling pre-match form features, oriented to the leak-free p1/p2 of matches_model.

Every rolling statistic uses `shift(1)` within a player's chronological match sequence,
so the current match is never part of its own features — the as-of guarantee holds by
construction. Head-to-head is accumulated in a single chronological pass.
"""

from collections import defaultdict

import duckdb
import numpy as np
import pandas as pd

from tennisdb.features.ordering import in_match_order

_YEAR_DAYS = 365.25
_FORM_WINDOWS = (10, 25)
_RECENT_DAYS = 14

_MATCHES_QUERY = """
SELECT
  m.match_id,
  m.edition_id,
  m.winner_id,
  m.loser_id,
  coalesce(m.match_date, e.start_date) AS order_date,
  m.round,
  winner.dob AS winner_dob,
  loser.dob AS loser_dob
FROM tennis.matches AS m
JOIN tennis.tournament_editions AS e USING (edition_id)
JOIN tennis.players AS winner ON winner.player_id = m.winner_id
JOIN tennis.players AS loser ON loser.player_id = m.loser_id
"""

_ORIENT_AND_INSERT = """
INSERT INTO analytics.form
SELECT
  f.match_id,
  CASE WHEN m.p1_won THEN f.w_win_pct_10 ELSE f.l_win_pct_10 END,
  CASE WHEN m.p1_won THEN f.w_win_pct_25 ELSE f.l_win_pct_25 END,
  CASE WHEN m.p1_won THEN f.l_win_pct_10 ELSE f.w_win_pct_10 END,
  CASE WHEN m.p1_won THEN f.l_win_pct_25 ELSE f.w_win_pct_25 END,
  CASE WHEN m.p1_won THEN f.w_rest_days ELSE f.l_rest_days END,
  CASE WHEN m.p1_won THEN f.l_rest_days ELSE f.w_rest_days END,
  CASE WHEN m.p1_won THEN f.w_matches_14d ELSE f.l_matches_14d END,
  CASE WHEN m.p1_won THEN f.l_matches_14d ELSE f.w_matches_14d END,
  CASE WHEN m.p1_won THEN f.w_prior_wins ELSE f.l_prior_wins END,
  f.w_prior_wins + f.l_prior_wins,
  CASE WHEN m.p1_won THEN f.w_age_years ELSE f.l_age_years END,
  CASE WHEN m.p1_won THEN f.l_age_years ELSE f.w_age_years END
FROM _form_rows AS f
JOIN tennis.matches_model AS m USING (match_id)
"""


def compute_form(matches: pd.DataFrame) -> pd.DataFrame:
    """Pure core: winner/loser-oriented pre-match form for every match."""
    ordered = in_match_order(matches)
    player_rows = _rolling_player_features(ordered)
    per_match = _join_both_sides(ordered, player_rows)
    per_match = _with_head_to_head(ordered, per_match)
    _add_ages(per_match)
    return per_match


def _rolling_player_features(ordered: pd.DataFrame) -> pd.DataFrame:
    long = _one_row_per_player(ordered)
    grouped = long.groupby("player_id", sort=False)
    for window in _FORM_WINDOWS:
        long[f"win_pct_{window}"] = grouped["won"].transform(
            lambda results: results.shift(1).rolling(window, min_periods=1).mean()
        )
    long["rest_days"] = (
        (long["order_date"] - grouped["order_date"].shift(1)).dt.days.astype("Int64")
    )
    long["matches_14d"] = grouped["order_date"].transform(_recent_match_count).astype("Int64")
    return long


def _one_row_per_player(ordered: pd.DataFrame) -> pd.DataFrame:
    sides = [
        pd.DataFrame(
            {
                "match_id": ordered["match_id"],
                "player_id": ordered[f"{role}_id"],
                "order_date": ordered["order_date"],
                "round_ordinal": ordered["round_ordinal"],
                "won": 1.0 if role == "winner" else 0.0,
            }
        )
        for role in ("winner", "loser")
    ]
    return (
        pd.concat(sides, ignore_index=True)
        .sort_values(["player_id", "order_date", "round_ordinal", "match_id"], kind="mergesort")
        .reset_index(drop=True)
    )


def _recent_match_count(order_dates: pd.Series) -> pd.Series:
    days = order_dates.to_numpy(dtype="datetime64[D]")
    horizon = days - np.timedelta64(_RECENT_DAYS, "D")
    prior_within_horizon = np.arange(len(days)) - np.searchsorted(days, horizon, side="left")
    return pd.Series(prior_within_horizon, index=order_dates.index)


def _join_both_sides(ordered: pd.DataFrame, player_rows: pd.DataFrame) -> pd.DataFrame:
    features = ["win_pct_10", "win_pct_25", "rest_days", "matches_14d"]
    columns = ["match_id", "player_id", *features]
    base = ["match_id", "winner_id", "loser_id", "order_date", "winner_dob", "loser_dob"]
    per_match = ordered[base].copy()
    for role, prefix in (("winner", "w"), ("loser", "l")):
        side = player_rows[columns].rename(
            columns={"player_id": f"{role}_id", **{name: f"{prefix}_{name}" for name in features}}
        )
        per_match = per_match.merge(side, on=["match_id", f"{role}_id"], how="left")
    return per_match


def _with_head_to_head(ordered: pd.DataFrame, per_match: pd.DataFrame) -> pd.DataFrame:
    prior_wins: dict[tuple[int, int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    records = []
    for match in ordered.itertuples(index=False):
        winner, loser = match.winner_id, match.loser_id
        pairing = prior_wins[(min(winner, loser), max(winner, loser))]
        records.append((match.match_id, pairing[winner], pairing[loser]))
        pairing[winner] += 1
    head_to_head = pd.DataFrame(records, columns=["match_id", "w_prior_wins", "l_prior_wins"])
    return per_match.merge(head_to_head, on="match_id", how="left")


def _add_ages(per_match: pd.DataFrame) -> None:
    for role, prefix in (("winner", "w"), ("loser", "l")):
        per_match[f"{prefix}_age_years"] = (
            (per_match["order_date"] - per_match[f"{role}_dob"]).dt.days / _YEAR_DAYS
        )


def build_form(connection: duckdb.DuckDBPyConnection) -> int:
    matches = connection.execute(_MATCHES_QUERY).fetch_df()
    per_match = compute_form(matches)
    connection.execute("DELETE FROM analytics.form")
    connection.register("_form_rows", per_match)
    try:
        return connection.execute(_ORIENT_AND_INSERT).fetchone()[0]
    finally:
        connection.unregister("_form_rows")
