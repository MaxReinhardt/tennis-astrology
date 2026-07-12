"""Map tennis-data player names ("Federer R.") to canonical Sackmann player ids.

Precedence: curated seed aliases (db/seed/player_aliases.csv, canonical ids —
WTA ids already offset) > exact folded-key match > rapidfuzz fallback. An alias
may keep several candidate ids ("Stephens S."); match resolution disambiguates
per row, where the edition's own matches make the choice structural.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass

import duckdb
from rapidfuzz import fuzz, process

from tennisdb import config
from tennisdb.ids import canonical_player_id
from tennisdb.resolve.text import fold, sackmann_alias_keys

FUZZY_THRESHOLD = 90
FUZZY_MARGIN = 3
PLAYER_SEED_FILE = "player_aliases.csv"

_ACTIVE_PLAYERS_SQL = """
    SELECT p.tour, p.player_id, p.name_first, p.name_last
    FROM staging.sackmann_players AS p
    JOIN (
        SELECT DISTINCT tour, winner_id AS player_id FROM staging.sackmann_matches
        WHERE tourney_date >= DATE '2000-01-01'
        UNION
        SELECT DISTINCT tour, loser_id FROM staging.sackmann_matches
        WHERE tourney_date >= DATE '2000-01-01'
    ) AS active USING (tour, player_id)
    WHERE p.name_last IS NOT NULL
"""

_TENNISDATA_NAMES_SQL = """
    SELECT DISTINCT tour, name FROM (
        SELECT tour, Winner AS name FROM staging.tennisdata_matches
        UNION
        SELECT tour, Loser FROM staging.tennisdata_matches
    )
    WHERE name IS NOT NULL
"""


@dataclass(frozen=True)
class AliasIndex:
    ids_by_key: dict[tuple[str, str], frozenset[int]]
    keys_by_tour: dict[str, list[str]]

    def exact(self, tour: str, folded_alias: str) -> frozenset[int] | None:
        return self.ids_by_key.get((tour, folded_alias))

    def fuzzy(self, tour: str, folded_alias: str) -> frozenset[int] | None:
        hits = self.fuzzy_candidates(tour, folded_alias, limit=5)
        if not hits:
            return None
        best_score = hits[0][1]
        ids: set[int] = set()
        for key, score, _ in hits:
            if score >= best_score - FUZZY_MARGIN:
                ids |= self.ids_by_key[(tour, key)]
        return frozenset(ids)

    def fuzzy_candidates(
        self, tour: str, folded_alias: str, limit: int, score_cutoff: float = FUZZY_THRESHOLD
    ) -> list:
        return process.extract(
            folded_alias,
            self.keys_by_tour.get(tour, []),
            scorer=fuzz.token_sort_ratio,
            score_cutoff=score_cutoff,
            limit=limit,
        )


@dataclass(frozen=True)
class PlayerAliasMap:
    candidates: dict[tuple[str, str], frozenset[int]]
    unresolved: frozenset[tuple[str, str]]

    def lookup(self, tour: str, name: str) -> frozenset[int] | None:
        return self.candidates.get((tour, fold(name)))

    def single_id_rows(self) -> list[tuple[str, str, int]]:
        return sorted(
            (alias, tour, next(iter(ids)))
            for (tour, alias), ids in self.candidates.items()
            if len(ids) == 1
        )


def build_alias_index(connection: duckdb.DuckDBPyConnection) -> AliasIndex:
    ids_by_key: dict[tuple[str, str], set[int]] = defaultdict(set)
    active_players = connection.execute(_ACTIVE_PLAYERS_SQL).fetchall()
    for tour, player_id, name_first, name_last in active_players:
        for key in sackmann_alias_keys(name_first, name_last):
            ids_by_key[(tour, key)].add(canonical_player_id(tour, player_id))
    keys_by_tour: dict[str, list[str]] = defaultdict(list)
    for tour, key in ids_by_key:
        keys_by_tour[tour].append(key)
    return AliasIndex(
        {key: frozenset(ids) for key, ids in ids_by_key.items()}, dict(keys_by_tour)
    )


def load_player_seed() -> dict[tuple[str, str], frozenset[int]]:
    path = config.SEED_DIR / PLAYER_SEED_FILE
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (row["tour"], fold(row["alias"])): frozenset({int(row["player_id"])})
            for row in csv.DictReader(handle)
            if row.get("player_id")
        }


def resolve_player_aliases(connection: duckdb.DuckDBPyConnection) -> PlayerAliasMap:
    seed = load_player_seed()
    index = build_alias_index(connection)
    candidates: dict[tuple[str, str], frozenset[int]] = {}
    unresolved: set[tuple[str, str]] = set()
    for tour, name in connection.execute(_TENNISDATA_NAMES_SQL).fetchall():
        folded = fold(name)
        ids = seed.get((tour, folded)) or index.exact(tour, folded) or index.fuzzy(tour, folded)
        if ids:
            candidates[(tour, folded)] = ids
        else:
            unresolved.add((tour, folded))
    return PlayerAliasMap(candidates, frozenset(unresolved))
