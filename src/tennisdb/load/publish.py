"""Publish the canonical tennis.* tables to a serving database (engine-agnostic).

A CanonicalSource yields rows from the local warehouse; a PublishSink writes them to
the target. Every canonical table is truncated child-first before any is copied
parent-first, so foreign keys hold throughout and — because load/supabase.py runs the
whole publish in one transaction — readers keep seeing the previous snapshot until a
single commit swaps in the new one. Each table's row count is reconciled against its
source; a mismatch raises PublishCountMismatch and aborts the publish.
"""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class CanonicalTable:
    name: str
    columns: tuple[str, ...]
    schema: str = "tennis"

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"


PLAYERS = CanonicalTable(
    "players",
    ("player_id", "tour", "full_name", "hand", "dob", "country_ioc", "height_cm", "wikidata_id"),
)
TOURNAMENT_EDITIONS = CanonicalTable(
    "tournament_editions",
    ("edition_id", "tour", "name", "surface", "level", "draw_size", "start_date", "season"),
)
MATCHES = CanonicalTable(
    "matches",
    (
        "match_id", "edition_id", "round", "best_of", "match_date", "winner_id", "loser_id",
        "score", "retirement", "walkover", "minutes", "winner_rank", "winner_rank_points",
        "loser_rank", "loser_rank_points",
    ),
)
MATCH_STATS = CanonicalTable(
    "match_stats",
    (
        "match_id", "w_ace", "w_df", "w_svpt", "w_1stin", "w_1stwon", "w_2ndwon", "w_svgms",
        "w_bpsaved", "w_bpfaced", "l_ace", "l_df", "l_svpt", "l_1stin", "l_1stwon", "l_2ndwon",
        "l_svgms", "l_bpsaved", "l_bpfaced",
    ),
)
RANKINGS = CanonicalTable("rankings", ("ranking_date", "tour", "player_id", "rank", "points"))
PLAYER_ALIASES = CanonicalTable("player_aliases", ("alias", "tour", "player_id"))
EDITION_ALIASES = CanonicalTable("edition_aliases", ("alias", "season", "tour", "edition_id"))
ODDS = CanonicalTable(
    "odds",
    ("match_id", "bookmaker", "winner_odds", "loser_odds", "is_closing", "source", "source_row"),
)

# Foreign-key dependency order (parent -> child); truncation walks it in reverse.
ALL_TABLES = (
    PLAYERS, TOURNAMENT_EDITIONS, MATCHES, MATCH_STATS, RANKINGS,
    PLAYER_ALIASES, EDITION_ALIASES, ODDS,
)
# rankings (5.5M rows) is left DuckDB-only by default: it alone would exhaust the
# Supabase free tier. scripts/publish.py --include-rankings publishes ALL_TABLES.
CORE_TABLES = tuple(table for table in ALL_TABLES if table is not RANKINGS)

ELO_PRE = CanonicalTable(
    "elo_pre",
    ("match_id", "p1_elo_pre", "p2_elo_pre", "p1_surface_elo_pre", "p2_surface_elo_pre", "surface"),
    schema="analytics",
)
FORM = CanonicalTable(
    "form",
    (
        "match_id", "p1_win_pct_10", "p1_win_pct_25", "p2_win_pct_10", "p2_win_pct_25",
        "p1_rest_days", "p2_rest_days", "p1_matches_14d", "p2_matches_14d",
        "h2h_p1_wins", "h2h_total", "p1_age_years", "p2_age_years",
    ),
    schema="analytics",
)
MARKET = CanonicalTable(
    "market",
    (
        "match_id", "bookmaker", "p1_market_prob", "p2_market_prob",
        "overround", "max_avg_dispersion",
    ),
    schema="analytics",
)
PLAYER_ASTRO = CanonicalTable(
    "player_astro",
    ("player_id", "zodiac_sign", "element", "birth_month"),
    schema="analytics",
)
# Feature tables carry no foreign keys, so truncation order is irrelevant.
FEATURE_TABLES = (ELO_PRE, FORM, MARKET, PLAYER_ASTRO)

PUBLISH_STEP = "publish:supabase"
FEATURE_PUBLISH_STEP = "publish:features"


class CanonicalSource(Protocol):
    def count(self, table: str) -> int: ...

    def rows(self, table: str, columns: Sequence[str]) -> Iterator[tuple]: ...


class PublishSink(Protocol):
    name: str

    def truncate(self, tables: Sequence[str]) -> None: ...

    def copy(self, table: str, columns: Sequence[str], rows: Iterable[tuple]) -> int: ...

    def count(self, table: str) -> int: ...

    def record_log(self, step: str, stats: dict) -> None: ...


class PublishCountMismatch(RuntimeError):
    pass


@dataclass
class PublishReport:
    sink_name: str
    table_rows: dict[str, int] = field(default_factory=dict)

    def stats(self) -> dict:
        return {"table_rows": self.table_rows}

    def summary_lines(self) -> list[str]:
        lines = [f"published to {self.sink_name}:"]
        lines.extend(f"  {table}: {count} rows" for table, count in self.table_rows.items())
        lines.append(
            f"  {sum(self.table_rows.values())} rows across {len(self.table_rows)} tables"
        )
        return lines


def publish_canonical(
    source: CanonicalSource, sink: PublishSink, tables: Sequence[CanonicalTable]
) -> PublishReport:
    sink.truncate([table.qualified for table in reversed(ALL_TABLES)])
    return _copy_all(source, sink, tables, PUBLISH_STEP)


def publish_features(source: CanonicalSource, sink: PublishSink) -> PublishReport:
    sink.truncate([table.qualified for table in FEATURE_TABLES])
    return _copy_all(source, sink, FEATURE_TABLES, FEATURE_PUBLISH_STEP)


def _copy_all(
    source: CanonicalSource, sink: PublishSink, tables: Sequence[CanonicalTable], step: str
) -> PublishReport:
    report = PublishReport(sink_name=sink.name)
    for table in tables:
        report.table_rows[table.qualified] = _copy_reconciled(source, sink, table)
    sink.record_log(step, report.stats())
    return report


def _copy_reconciled(
    source: CanonicalSource, sink: PublishSink, table: CanonicalTable
) -> int:
    copied = sink.copy(table.qualified, table.columns, source.rows(table.qualified, table.columns))
    expected = source.count(table.qualified)
    loaded = sink.count(table.qualified)
    if not copied == expected == loaded:
        raise PublishCountMismatch(
            f"{table.name}: source has {expected}, copied {copied}, target has {loaded}"
        )
    return loaded
