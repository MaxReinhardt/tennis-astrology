"""Print the most frequent unmatched odds rows with paste-ready seed CSV lines.

Reads data/quality/unmatched_odds.csv (written by `build_db.py --resolve`) and the
warehouse, then for each frequent miss suggests candidate seed rows for
db/seed/player_aliases.csv and db/seed/edition_aliases.csv. Verify a suggestion
against the printed full name / edition before pasting it.
"""

import csv
import sys
from collections import Counter, defaultdict
from datetime import date

import duckdb

from tennisdb import config
from tennisdb.resolve.pipeline import UNMATCHED_FILE
from tennisdb.resolve.players import build_alias_index, resolve_player_aliases
from tennisdb.resolve.text import fold
from tennisdb.resolve.tournaments import (
    candidate_pools,
    group_alias,
    resolve_editions,
    scored_candidates,
)

TOP_NAMES = 50
TOP_GROUPS = 25
SUGGESTION_CUTOFF = 55


def main() -> int:
    unmatched_path = config.QUALITY_DIR / UNMATCHED_FILE
    if not unmatched_path.exists():
        print(f"{unmatched_path} missing — run `build_db.py --resolve` first")
        return 1
    with unmatched_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    connection = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    try:
        report_unresolved_players(connection, rows)
        report_unresolved_editions(connection, rows)
        report_no_candidate_groups(connection, rows)
        report_remaining_reasons(rows)
    finally:
        connection.close()
    return 0


def report_unresolved_players(connection, rows) -> None:
    aliases = resolve_player_aliases(connection)
    index = build_alias_index(connection)
    full_names = dict(
        connection.execute("SELECT player_id, full_name FROM tennis.players").fetchall()
    )
    mentions: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if row["reason"] != "player_unresolved":
            continue
        for name in (row["winner"], row["loser"]):
            if aliases.lookup(row["tour"], name) is None:
                mentions[(row["tour"], name)] += 1

    print(f"== player_unresolved: top {TOP_NAMES} of {len(mentions)} names ==")
    for (tour, name), count in mentions.most_common(TOP_NAMES):
        print(f"# {count} rows  {tour}  {name!r}")
        hits = index.fuzzy_candidates(tour, fold(name), limit=3, score_cutoff=SUGGESTION_CUTOFF)
        for key, score, _ in hits:
            for player_id in sorted(index.ids_by_key[(tour, key)]):
                full_name = full_names.get(player_id)
                print(f"{name},{tour},{player_id},{full_name}  <- score {score:.0f}")
        if not hits:
            print("  (no fuzzy candidate — search staging.sackmann_players manually)")


def report_unresolved_editions(connection, rows) -> None:
    _report_edition_groups(
        connection,
        _group_rows(row for row in rows if row["reason"] == "edition_unresolved"),
        title="edition_unresolved",
    )


def report_no_candidate_groups(connection, rows) -> None:
    """no_candidate rows clustering on one group usually mean the whole event
    resolved to the wrong edition — show where it went and the alternatives."""
    editions = resolve_editions(connection)
    groups = _group_rows(row for row in rows if row["reason"] == "no_candidate")
    frequent = {group: stats for group, stats in groups.items() if stats["count"] >= 10}
    print(f"\n== no_candidate clusters (>= 10 rows): {len(frequent)} groups ==")
    for (tour, season, tournament, location), stats in sorted(
        frequent.items(), key=lambda item: -item[1]["count"]
    ):
        resolved_to = editions.lookup(tour, season, tournament, location)
        print(
            f"# {stats['count']} rows  {tour} {season}  {tournament} @ {location} "
            f"-> currently {resolved_to}"
        )
        _print_candidates(connection, tour, season, tournament, location, stats)


def _report_edition_groups(connection, groups, title) -> None:
    print(f"\n== {title}: top {TOP_GROUPS} of {len(groups)} groups ==")
    for (tour, season, tournament, location), stats in sorted(
        groups.items(), key=lambda item: -item[1]["count"]
    )[:TOP_GROUPS]:
        print(f"# {stats['count']} rows  {tour} {season}  {tournament} @ {location} "
              f"[{stats['date_min']}..{stats['date_max']}]")
        _print_candidates(connection, tour, season, tournament, location, stats)


def _print_candidates(connection, tour, season, tournament, location, stats) -> None:
    pools = _cached_pools(connection)
    scored = scored_candidates(
        pools.get((tour, season), []), tournament, location,
        stats["date_min"], stats["date_max"],
    )
    for score, candidate in scored[:3]:
        print(
            f"{group_alias(tournament, location)},{season},{tour},{candidate.edition_id},"
            f"{candidate.name} start {candidate.start_date} score {score:.0f}"
        )
    if not scored:
        print("  (no edition candidate in the date window)")


def _group_rows(rows) -> dict:
    groups: dict[tuple, dict] = defaultdict(
        lambda: {"count": 0, "date_min": None, "date_max": None}
    )
    for row in rows:
        key = (row["tour"], int(row["season"]), row["tournament"], row["location"])
        stats = groups[key]
        stats["count"] += 1
        row_date = date.fromisoformat(row["date"]) if row["date"] else None
        if row_date:
            stats["date_min"] = min(filter(None, (stats["date_min"], row_date)))
            stats["date_max"] = max(filter(None, (stats["date_max"], row_date)))
    return dict(groups)


_POOLS_CACHE = {}


def _cached_pools(connection):
    if "pools" not in _POOLS_CACHE:
        _POOLS_CACHE["pools"] = candidate_pools(connection)
    return _POOLS_CACHE["pools"]


def report_remaining_reasons(rows) -> None:
    for reason in ("winner_mismatch", "ambiguous"):
        subset = [row for row in rows if row["reason"] == reason]
        print(f"\n== {reason}: {len(subset)} rows ==")
        for row in subset[:15]:
            print(f"  {row['tour']} {row['season']} {row['tournament']}: "
                  f"{row['winner']} d. {row['loser']} ({row['date']}, {row['round']})")


if __name__ == "__main__":
    sys.exit(main())
