"""DuckDB adapter for OpportunitySource. Runs the shared opportunity query
(opportunity_query.py) against the local warehouse; the Postgres adapter runs the same
query against Supabase, so both yield identical events."""

from collections.abc import Iterator

import duckdb

from tennisdb.backtest.domain import MatchEvent
from tennisdb.backtest.opportunity_query import DUCKDB_PLACEHOLDER, build_query, events_from_rows
from tennisdb.backtest.request import BacktestRequest


class DuckDbOpportunitySource:
    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self._connection = connection

    @classmethod
    def open(cls, connection: duckdb.DuckDBPyConnection) -> "DuckDbOpportunitySource":
        return cls(connection)

    def events(self, request: BacktestRequest) -> Iterator[MatchEvent]:
        query, params = build_query(request, DUCKDB_PLACEHOLDER)
        cursor = self._connection.execute(query, params)
        columns = [column[0] for column in cursor.description]
        rows = (dict(zip(columns, values, strict=True)) for values in cursor.fetchall())
        return events_from_rows(rows)
