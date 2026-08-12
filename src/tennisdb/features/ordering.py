"""Deterministic chronological match ordering shared by the sequential feature builders.

Ordering by (date, edition, round, match_id) means earlier tournament rounds update a
player's state before later ones, and the order never depends on how rows arrived — the
foundation of the as-of discipline.
"""

import pandas as pd

ROUND_ORDINAL = {
    "Q1": 0, "Q2": 1, "Q3": 2, "BR": 3, "RR": 3,
    "R128": 4, "R64": 5, "R32": 6, "R16": 7, "QF": 8, "SF": 9, "F": 10,
}  # fmt: skip
_DEFAULT_ROUND_ORDINAL = 3
_SORT_KEYS = ["order_date", "edition_id", "round_ordinal", "match_id"]


def in_match_order(matches: pd.DataFrame) -> pd.DataFrame:
    """Return a copy carrying a `round_ordinal` column, sorted chronologically. Requires
    `order_date`, `edition_id`, `round`, and `match_id` columns."""
    ordered = matches.copy()
    ordered["round_ordinal"] = (
        ordered["round"].map(ROUND_ORDINAL).fillna(_DEFAULT_ROUND_ORDINAL).astype(int)
    )
    return ordered.sort_values(_SORT_KEYS, kind="mergesort").reset_index(drop=True)
