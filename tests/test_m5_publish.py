"""M5: engine-agnostic publish use case — truncation, copy order, reconciliation."""

import pytest

from tennisdb.load.publish import (
    ALL_TABLES,
    CORE_TABLES,
    MATCHES,
    PLAYERS,
    PUBLISH_STEP,
    RANKINGS,
    PublishCountMismatch,
    publish_canonical,
)

pytestmark = pytest.mark.m5

_FK_PARENTS = {
    "matches": {"players", "tournament_editions"},
    "match_stats": {"matches"},
    "rankings": {"players"},
    "player_aliases": {"players"},
    "edition_aliases": {"tournament_editions"},
    "odds": {"matches"},
}


class FakeCanonicalSource:
    def __init__(self, row_counts: dict[str, int]):
        self._row_counts = row_counts

    def count(self, table: str) -> int:
        return self._row_counts.get(table, 0)

    def rows(self, table: str, columns):
        for index in range(self._row_counts.get(table, 0)):
            yield (index,)


class FakePublishSink:
    name = "fake"

    def __init__(self, drop_last_from: str | None = None):
        self._drop_last_from = drop_last_from
        self.truncated: list[str] = []
        self.copy_order: list[str] = []
        self.stored: dict[str, int] = {}
        self.logged: list[tuple[str, dict]] = []

    def truncate(self, tables):
        self.truncated = list(tables)

    def copy(self, table, columns, rows):
        received = list(rows)
        if table == self._drop_last_from:
            received = received[:-1]
        self.copy_order.append(table)
        self.stored[table] = len(received)
        return len(received)

    def count(self, table):
        return self.stored.get(table, 0)

    def record_log(self, step, stats):
        self.logged.append((step, stats))


def _source_of(tables, rows_per_table: int) -> FakeCanonicalSource:
    return FakeCanonicalSource({table.name: rows_per_table for table in tables})


def test_publish_truncates_every_canonical_table_child_first():
    sink = FakePublishSink()

    publish_canonical(_source_of(CORE_TABLES, 1), sink, CORE_TABLES)

    assert sink.truncated == [table.name for table in reversed(ALL_TABLES)]


def test_publish_copies_selected_tables_parent_before_child():
    sink = FakePublishSink()

    publish_canonical(_source_of(CORE_TABLES, 2), sink, CORE_TABLES)

    assert sink.copy_order == [table.name for table in CORE_TABLES]


def test_publish_reports_reconciled_row_count_per_table():
    sink = FakePublishSink()

    report = publish_canonical(_source_of(CORE_TABLES, 4), sink, CORE_TABLES)

    assert report.table_rows == {table.name: 4 for table in CORE_TABLES}


def test_publish_raises_when_target_count_differs_from_source():
    sink = FakePublishSink(drop_last_from=MATCHES.name)

    with pytest.raises(PublishCountMismatch, match="matches"):
        publish_canonical(_source_of(CORE_TABLES, 3), sink, CORE_TABLES)


def test_publish_logs_publish_step_with_table_rows():
    sink = FakePublishSink()

    publish_canonical(_source_of(CORE_TABLES, 1), sink, CORE_TABLES)

    assert len(sink.logged) == 1
    step, stats = sink.logged[0]
    assert step == PUBLISH_STEP
    assert stats["table_rows"][MATCHES.name] == 1


def test_core_tables_exclude_rankings_but_all_tables_include_it():
    assert RANKINGS not in CORE_TABLES
    assert RANKINGS in ALL_TABLES


def test_all_tables_order_places_foreign_key_parents_before_children():
    position = {table.name: index for index, table in enumerate(ALL_TABLES)}

    for child, parents in _FK_PARENTS.items():
        for parent in parents:
            assert position[parent] < position[child], f"{parent} must precede {child}"


def test_publish_report_summary_lines_name_tables_and_total():
    sink = FakePublishSink()

    report = publish_canonical(_source_of((PLAYERS,), 2), sink, (PLAYERS,))

    lines = report.summary_lines()
    assert any("tennis.players: 2 rows" in line for line in lines)
