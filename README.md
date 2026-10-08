# tennis-astrology

A tennis match-result & betting-odds database (Supabase + DuckDB) and a
financial-markets-style backtesting environment for testing betting hypotheses —
including, per the repo name, astrological ones (as a multiple-testing discipline demo).

**Start here: [PLAN.md](PLAN.md)** — the full implementation plan, structured as
milestones M0–M8, each with verifiable acceptance criteria.

## Summary

- **Data**: Jeff Sackmann's `tennis_atp` / `tennis_wta` (results, players, rankings)
  merged with tennis-data.co.uk (bookmaker closing odds, ATP 2001+, WTA 2007+).
- **Storage**: local DuckDB warehouse for ETL/backtests; Supabase (Postgres) as the
  published system of record.
- **Analytics**: Elo + form + market features, walk-forward backtesting engine with
  Kelly staking, CLV, bootstrap confidence intervals, and a pre-registered
  hypothesis-study workflow.

## Status

M0–M7 implemented (project scaffolding through the backtesting engine); M8's
hypothesis-research workflow is next. Run `uv run pytest` to check the full suite, or
`uv run pytest -m m7` for just the backtesting engine.

One manual prerequisite before milestone M3/M5: create a free Supabase project and put
its Postgres connection string in `.env` (see `.env.example`).

## Backtesting

```bash
uv run python scripts/build_db.py --all --features   # build the warehouse once
uv run python scripts/run_backtest.py --strategy elo_value --from 2015 --to 2019 \
    --stake kelly:0.25
```

Each run writes `data/backtests/<run_id>/{result.json, equity_curve.csv, bets.csv}` and
logs a summary row to `tennis.ingest_log`.

**Train/validation/test discipline.** Any strategy parameter you tune (θ in `elo_value`,
a price band in `back_underdogs`, a staking fraction) must be chosen using seasons
≤ 2018 only. Seasons 2019 onward are the held-out test set: touch them only for the
final, pre-registered evaluation of a strategy you have already fixed. This is
backtesting's version of a train/test split, and it exists to prevent the kind of
p-hacking that makes most "edges" vanish out of sample — see M8's hypothesis template
for the full protocol.

### Driving the engine from JSON (and, later, natural language)

The engine takes one flat, JSON-serializable request and returns pre-formatted,
labelled metrics — designed so a UI, or an LLM wrapper translating a question into a
request, needs no real transformation step in either direction:

```bash
uv run python scripts/run_backtest.py --catalog          # the full machine-readable
                                                           # contract: every strategy,
                                                           # parameter, filter, stake
                                                           # rule and output metric
echo '{"strategy": "back_underdogs",
       "filters": {"surfaces": ["Clay"], "from_season": 2015, "to_season": 2018}}' \
  | uv run python scripts/run_backtest.py --request - --json
```

An invalid request (unknown strategy, out-of-band parameter, …) is rejected with a
message naming the allowed values, so a caller — human or model — can self-correct
without a second round trip.
