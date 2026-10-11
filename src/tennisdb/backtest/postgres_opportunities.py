"""Postgres/Supabase adapter for OpportunitySource. Runs the same query as the DuckDB
adapter (opportunity_query.py) over a psycopg connection, so a deployed API with no
local warehouse yields events identical to a local run."""

from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from tennisdb.backtest.domain import MatchEvent
from tennisdb.backtest.opportunity_query import (
    POSTGRES_PLACEHOLDER,
    build_query,
    events_from_rows,
)
from tennisdb.backtest.request import BacktestRequest


class PostgresOpportunitySource:
    def __init__(self, connection: psycopg.Connection):
        self._connection = connection

    @classmethod
    def connect(cls, url: str) -> "PostgresOpportunitySource":
        """prepare_threshold=None because Supabase's transaction pooler (port 6543)
        cannot hold server-side prepared statements across transactions."""
        connection = psycopg.connect(url, row_factory=dict_row, prepare_threshold=None)
        connection.read_only = True
        return cls(connection)

    def events(self, request: BacktestRequest) -> Iterator[MatchEvent]:
        query, params = build_query(request, POSTGRES_PLACEHOLDER)
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        self._connection.rollback()
        return events_from_rows(rows)

    def close(self) -> None:
        self._connection.close()
