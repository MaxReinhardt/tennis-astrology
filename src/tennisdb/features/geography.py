"""Tournament host geography, derived from the M4 edition_aliases host-city token.

edition_aliases.alias is group_alias(tournament, location) == "<tournament> @ <city>"
(resolve.tournaments.group_alias); every edition with odds resolves to exactly one city
this way, so the host city needs no new matching step — only a country lookup on top of
it. Host country is a hand-seeded mapping (db/seed/host_countries.csv) over the ~200
distinct cities; editions whose city has no seed entry get a null country rather than a
guess, and the M8 S4 study filters those out explicitly.
"""

import csv

import duckdb

from tennisdb import config

HOST_COUNTRY_SEED_FILE = "host_countries.csv"

_EDITION_HOST_CITY_QUERY = """
SELECT edition_id, trim(split_part(alias, ' @ ', 2)) AS host_city
FROM tennis.edition_aliases
WHERE alias LIKE '%@%'
"""


def load_host_countries() -> dict[str, str]:
    path = config.SEED_DIR / HOST_COUNTRY_SEED_FILE
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["host_city"]: row["country_ioc"]
            for row in csv.DictReader(handle)
            if row.get("country_ioc")
        }


def build_edition_geo(connection: duckdb.DuckDBPyConnection) -> int:
    host_countries = load_host_countries()
    rows = connection.execute(_EDITION_HOST_CITY_QUERY).fetchall()
    connection.execute("DELETE FROM analytics.edition_geo")
    connection.executemany(
        "INSERT INTO analytics.edition_geo (edition_id, host_city, host_country_ioc) "
        "VALUES (?, ?, ?)",
        [(edition_id, city, host_countries.get(city)) for edition_id, city in rows],
    )
    return len(rows)
