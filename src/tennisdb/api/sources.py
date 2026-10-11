"""Composition root for where the API reads matches from: Supabase when a serving
connection is configured (the deployed app), otherwise the local DuckDB warehouse."""

from collections.abc import Iterator
from contextlib import contextmanager

import duckdb

from tennisdb import config
from tennisdb.backtest.engine import OpportunitySource
from tennisdb.backtest.opportunities import DuckDbOpportunitySource
from tennisdb.backtest.postgres_opportunities import PostgresOpportunitySource


def source_name() -> str:
    return "supabase" if config.SUPABASE_READ_URL else "duckdb"


@contextmanager
def open_source() -> Iterator[OpportunitySource]:
    if config.SUPABASE_READ_URL:
        remote = PostgresOpportunitySource.connect(config.SUPABASE_READ_URL)
        try:
            yield remote
        finally:
            remote.close()
        return
    local = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    try:
        yield DuckDbOpportunitySource.open(local)
    finally:
        local.close()
