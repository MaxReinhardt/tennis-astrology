"""Map tennis-data (Tournament, Location, season, tour) groups to Sackmann edition ids.

Sackmann has no per-match dates, so the "±3-day tolerance" applies to the edition
window: a group's match dates must overlap [start_date − 3, start_date + 17]
(17 = 14-day slam plus grace). Name scoring takes the better of Tournament and
Location against the Sackmann edition name — Location wins for city-named events,
Tournament for event-named ones — and token_set_ratio absorbs sponsor tokens.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

import duckdb
from rapidfuzz import fuzz

from tennisdb import config
from tennisdb.resolve.text import fold

EDITION_SEED_FILE = "edition_aliases.csv"
SCORE_FLOOR_SOLE_CANDIDATE = 50
SCORE_THRESHOLD = 60
SCORE_MARGIN = 10
LOCATION_WEIGHT = 0.9
WINDOW_BEFORE = timedelta(days=3)
WINDOW_AFTER = timedelta(days=17)

# Stable naming differences between the sources; season-independent, so they live
# here rather than in the per-season seed CSV.
_TOURNAMENT_SYNONYMS = {
    "french open": "roland garros",
    "masters cup": "tour finals",
    "canadian open": "canada masters",
    "rogers cup": "canada masters",
    "rogers masters": "canada masters",
    "montreal tms": "canada masters",
    "toronto tms": "canada masters",
}

_GROUPS_SQL = """
    SELECT tour, season, Tournament, Location, min("Date"), max("Date")
    FROM staging.tennisdata_matches
    GROUP BY tour, season, Tournament, Location
"""

_EDITIONS_SQL = """
    SELECT edition_id, tour, season, name, start_date
    FROM tennis.tournament_editions
    WHERE season IS NOT NULL AND (level IS NULL OR level <> 'D')
"""

GroupKey = tuple[str, int, str, str]


@dataclass(frozen=True)
class EditionCandidate:
    edition_id: str
    name: str
    start_date: date | None


@dataclass(frozen=True)
class EditionAliasMap:
    editions: dict[GroupKey, str]
    unresolved: frozenset[GroupKey]

    def lookup(self, tour: str, season: int, tournament: str, location: str) -> str | None:
        return self.editions.get((tour, int(season), tournament, location))

    def alias_rows(self) -> list[tuple[str, int, str, str]]:
        deduped = {
            (group_alias(tournament, location), season, tour): edition_id
            for (tour, season, tournament, location), edition_id in self.editions.items()
        }
        return sorted(
            (alias, season, tour, edition_id)
            for (alias, season, tour), edition_id in deduped.items()
        )


def group_alias(tournament: str, location: str) -> str:
    return f"{fold(tournament)} @ {fold(location)}"


def load_edition_seed() -> dict[tuple[str, int, str], str]:
    path = config.SEED_DIR / EDITION_SEED_FILE
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (fold(row["alias"]), int(row["season"]), row["tour"]): row["edition_id"]
            for row in csv.DictReader(handle)
            if row.get("edition_id")
        }


def resolve_editions(connection: duckdb.DuckDBPyConnection) -> EditionAliasMap:
    seed = load_edition_seed()
    pools = candidate_pools(connection)
    editions: dict[GroupKey, str] = {}
    unresolved: set[GroupKey] = set()
    for tour, season, tournament, location, date_min, date_max in (
        connection.execute(_GROUPS_SQL).fetchall()
    ):
        group = (tour, int(season), tournament, location)
        seeded = seed.get((group_alias(tournament, location), int(season), tour))
        scored = scored_candidates(
            pools.get((tour, int(season)), []), tournament, location, date_min, date_max
        )
        chosen = seeded or _accept(scored)
        if chosen:
            editions[group] = chosen
        else:
            unresolved.add(group)
    return EditionAliasMap(editions, frozenset(unresolved))


def candidate_pools(
    connection: duckdb.DuckDBPyConnection,
) -> dict[tuple[str, int], list[EditionCandidate]]:
    pools: dict[tuple[str, int], list[EditionCandidate]] = defaultdict(list)
    for edition_id, tour, season, name, start_date in connection.execute(_EDITIONS_SQL).fetchall():
        pools[(tour, int(season))].append(EditionCandidate(edition_id, name, start_date))
    return dict(pools)


def scored_candidates(
    pool: list[EditionCandidate],
    tournament: str,
    location: str,
    date_min: date | None,
    date_max: date | None,
) -> list[tuple[float, EditionCandidate]]:
    in_window = (
        candidate for candidate in pool
        if _windows_overlap(candidate.start_date, date_min, date_max)
    )
    return sorted(
        ((_name_score(candidate, tournament, location), candidate) for candidate in in_window),
        key=lambda pair: pair[0],
        reverse=True,
    )


def _windows_overlap(start_date: date | None, date_min: date | None, date_max: date | None) -> bool:
    if start_date is None or date_min is None or date_max is None:
        return True
    return date_min <= start_date + WINDOW_AFTER and date_max >= start_date - WINDOW_BEFORE


def _accept(scored: list[tuple[float, EditionCandidate]]) -> str | None:
    if not scored:
        return None
    best_score, best = scored[0]
    if len(scored) == 1:
        return best.edition_id if best_score >= SCORE_FLOOR_SOLE_CANDIDATE else None
    runner_up_score = scored[1][0]
    if best_score >= SCORE_THRESHOLD and best_score - runner_up_score >= SCORE_MARGIN:
        return best.edition_id
    return None


def _name_score(candidate: EditionCandidate, tournament: str, location: str) -> float:
    """Tournament matches at full weight, Location slightly discounted: a group like
    ("Australian Open", "Melbourne") must prefer the eponymous edition over a
    city-named neighbour ("Melbourne") that Location alone would tie with."""
    folded_name = fold(candidate.name)
    folded_tournament = fold(tournament)
    scores = [
        fuzz.token_set_ratio(folded_tournament, folded_name),
        LOCATION_WEIGHT * fuzz.token_set_ratio(fold(location), folded_name),
    ]
    synonym = _TOURNAMENT_SYNONYMS.get(folded_tournament)
    if synonym:
        scores.append(fuzz.token_set_ratio(synonym, folded_name))
    return max(scores)
