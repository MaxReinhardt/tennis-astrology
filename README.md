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

Planning stage — no code yet. Implementation follows PLAN.md milestone by milestone.

One manual prerequisite before milestone M3/M5: create a free Supabase project and put
its Postgres connection string in `.env` (see `.env.example` once M0 lands).
