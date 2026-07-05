# Tennis Match & Betting Database — Implementation Plan

Goal: build a clean, reproducible database of professional tennis match results **and**
historical betting odds, hosted on Supabase (Postgres), plus a local Python environment
for feature engineering and **financial-markets-style backtesting** of betting
hypotheses (odds = prices, bets = trades, closing line = market consensus).

This plan is written for agent implementation: it is split into milestones **M0–M8**,
each with explicit deliverables and a **Verify** block containing commands and expected
results. A milestone is done only when its Verify block passes. Implement milestones in
order; later milestones assume earlier ones.

---

## Guiding decisions (made up front so the agent doesn't re-litigate them)

1. **Sources: merge existing curated datasets rather than scraping.**
   Scraping live sites (Sofascore, Flashscore, ATP.com) is fragile and ToS-problematic.
   Two high-quality, free, long-established sources cover everything we need:
   - **Jeff Sackmann's GitHub repos** (`JeffSackmann/tennis_atp`, `JeffSackmann/tennis_wta`):
     match results 1968–present with player IDs, rankings, surfaces, rounds, and
     in-match statistics. License: CC BY-NC-SA 4.0 (non-commercial research use — fine here).
   - **tennis-data.co.uk**: per-season CSV/XLSX files with **bookmaker odds**
     (Bet365, Pinnacle, plus Max/Avg across books) for ATP from 2001 and WTA from 2007.
   These must be **entity-resolved and merged** (different player-name and tournament-name
   conventions) — that merge is the core data-engineering work of this project (M4).
   Scraping remains a documented *extension*, not part of the core build.

2. **Local-first ETL, Supabase as the serving layer.**
   Raw files are downloaded to `data/raw/` (gitignored), transformed locally with
   Python + DuckDB (fast, testable, free), and only the **clean canonical tables** are
   published to Supabase. Backtests read from a local DuckDB mirror for speed;
   Supabase is the durable, queryable system of record (SQL editor, dashboards, API).

3. **Canonical match identity comes from Sackmann; odds attach to it.**
   Sackmann rows have stable player IDs and tournament IDs — they define the `matches`
   table. tennis-data rows are matched onto them and contribute the `odds` rows.

4. **No lookahead by construction.** Matches are stored winner/loser as sourced, but the
   modeling/backtest view exposes them as randomized `p1`/`p2` with a `p1_won` label, and
   every feature table is keyed by "information available strictly before match start".

5. **Python 3.12, `uv` for env management, `pytest` for verification.** All Verify blocks
   are also encoded as pytest tests where possible, so `pytest -m mX` re-checks milestone X.

6. **Secrets** (Supabase URL / service key / DB password) live only in `.env`
   (gitignored); `.env.example` documents required variables. The agent must never
   commit credentials.

---

## Repository layout (created in M0)

```
.
├── PLAN.md                    # this file
├── README.md
├── pyproject.toml             # uv-managed; deps pinned
├── .env.example               # SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL
├── .gitignore                 # data/, .env, *.duckdb, __pycache__ ...
├── data/                      # gitignored
│   ├── raw/sackmann/          # cloned CSVs (atp + wta)
│   ├── raw/tennisdata/        # yearly odds files
│   └── warehouse.duckdb       # local staging + analytics DB
├── db/
│   └── migrations/            # 001_core.sql, 002_odds.sql, ... (plain SQL, idempotent)
├── src/tennisdb/
│   ├── config.py              # env loading, paths, constants
│   ├── ingest/                # sackmann.py, tennisdata.py  (download + parse to staging)
│   ├── resolve/               # players.py, tournaments.py, matches.py (entity resolution)
│   ├── load/                  # supabase.py (publish canonical tables), duckdb_mirror.py
│   ├── quality/               # checks.py (data-quality suite, returns pass/fail report)
│   ├── features/              # elo.py, form.py, market.py (implied probs, vig removal)
│   └── backtest/
│       ├── engine.py          # event-driven walk-forward loop
│       ├── staking.py         # flat, fractional Kelly
│       ├── metrics.py         # ROI, drawdown, CLV, Brier, log-loss, bootstrap CIs
│       └── strategies/        # base.py + concrete strategies
├── scripts/                   # thin CLIs: ingest_all.py, build_db.py, publish.py, run_backtest.py
├── notebooks/                 # exploration only, never load-bearing
└── tests/                     # pytest; markers m0..m8 mirror milestones
```

---

## M0 — Project scaffolding & environment

**Tasks**
1. Create the layout above; `pyproject.toml` with dependencies:
   `pandas`, `duckdb`, `httpx`, `openpyxl`, `python-dotenv`, `psycopg[binary]`,
   `rapidfuzz` (name matching), `pytest`, `ruff`.
2. `.gitignore` covering `data/`, `.env`, `*.duckdb`, caches.
3. `src/tennisdb/config.py`: resolves project paths, loads `.env`, exposes
   `RAW_DIR`, `DUCKDB_PATH`, `SUPABASE_DB_URL` (may be unset until M3).
4. A trivial smoke test `tests/test_m0_smoke.py`.

**Verify (M0)**
```bash
uv sync                     # resolves and installs cleanly
uv run ruff check .         # no errors
uv run pytest -m m0         # smoke test passes (imports tennisdb, paths exist)
```

---

## M1 — Raw data acquisition

**Tasks**
1. `ingest/sackmann.py`: shallow-clone (or tarball-download) `JeffSackmann/tennis_atp`
   and `JeffSackmann/tennis_wta` into `data/raw/sackmann/`. Needed files:
   - `atp_matches_1968.csv` … `atp_matches_<current>.csv` (main tour; qual/challenger
     files are optional extras, off by default)
   - `wta_matches_1968.csv` … current
   - `atp_players.csv`, `wta_players.csv` (player id, name, hand, DOB, country, height)
   - `atp_rankings_*.csv`, `wta_rankings_*.csv`
2. `ingest/tennisdata.py`: download yearly files from tennis-data.co.uk
   (`http://www.tennis-data.co.uk/<year>/<year>.xlsx` for ATP,
   `http://www.tennis-data.co.uk/<year>w/<year>.xlsx` for WTA — confirm exact URL
   pattern from the site's index pages at run time; they are stable but the extension
   flips between .xls/.xlsx/.csv across years). ATP: 2001–present; WTA: 2007–present.
3. Both ingesters are **idempotent** (skip existing files unless `--force`) and write a
   manifest `data/raw/manifest.json` (file, source URL, sha256, row count, downloaded_at).
4. `scripts/ingest_all.py` runs both.

**Verify (M1)** — `uv run pytest -m m1`, which asserts:
- Every expected yearly file exists and parses.
- Sackmann ATP main-tour matches total **> 180,000** rows; WTA **> 150,000**.
- `atp_players.csv` has **> 50,000** rows and non-null DOB for the vast majority of
  post-1980 tour players.
- tennis-data ATP files: **≥ 2,000 rows per season** for every season 2001–2019
  (later seasons: ≥ 1,500 to allow for the current partial year), each with at least
  one odds pair (`B365W/B365L` or `PSW/PSL` or `AvgW/AvgL`) non-null on **≥ 90%** of rows.
- Manifest entries exist for every file, checksums stable across a re-run (idempotency).

---

## M2 — Staging layer in DuckDB

**Tasks**
1. Load all raw files into DuckDB schema `staging` with **minimal, lossless** typing:
   `staging.sackmann_matches` (add columns `tour` = atp/wta, `source_file`),
   `staging.sackmann_players`, `staging.sackmann_rankings`,
   `staging.tennisdata_matches` (normalize the messy per-year column drift: some years
   lack `PSW/PSL`, older years have extra bookmakers — union into one wide table with
   NULLs; add `tour`, `season`, `source_file`, `source_row` for provenance).
2. Normalize primitive values at staging time only where unambiguous:
   dates → DATE, odds → DOUBLE (coerce '', 0 and obvious garbage to NULL), surfaces to
   the four canonical values (Hard/Clay/Grass/Carpet), rounds to a canonical enum
   (F, SF, QF, R16, R32, R64, R128, RR, Q1–Q3, BR).
3. `scripts/build_db.py --stage` builds staging from raw + manifest.

**Verify (M2)** — `uv run pytest -m m2`:
- Row counts in staging equal manifest row counts (± header rows) per file.
- `staging.tennisdata_matches`: `Winner`/`Loser` non-null on 100% of rows; date parse
  failures = 0; odds values all in **[1.001, 1001)** or NULL.
- Surface distribution sanity: Hard is the most common surface in both sources post-2000.
- Round enum covers ≥ 99.9% of rows (unmapped values listed, not silently dropped).

---

## M3 — Canonical schema & Supabase provisioning

**Tasks**
1. Write idempotent SQL migrations in `db/migrations/` defining schema `tennis`:

```sql
-- 001_core.sql (sketch — final DDL to be fleshed out by the agent)
players(
  player_id      int  PK,          -- Sackmann ID (namespaced: atp ids and wta ids don't collide after offsetting wta by +10_000_000)
  tour           text CHECK (tour in ('atp','wta')),
  full_name      text NOT NULL,
  hand           text, dob date, country_ioc text, height_cm int
)
tournament_editions(
  edition_id     text PK,          -- Sackmann tourney_id, e.g. '2019-580'
  tour text, name text, surface text, level text, draw_size int,
  start_date date, season int
)
matches(
  match_id       text PK,          -- '<edition_id>-<match_num>'
  edition_id     text FK, round text, best_of int, match_date date,
  winner_id int FK players, loser_id int FK players,
  score text, retirement bool, walkover bool, minutes int,
  winner_rank int, winner_rank_points int, loser_rank int, loser_rank_points int
)
match_stats(match_id FK PK, w_ace int, w_df int, w_svpt int, ... l_bpfaced int)
rankings(ranking_date date, tour text, player_id int FK, rank int, points int,
         PK (ranking_date, player_id))

-- 002_odds.sql
odds(
  match_id text FK, bookmaker text,       -- 'B365','PS','Max','Avg'
  winner_odds numeric, loser_odds numeric,
  is_closing bool DEFAULT true,           -- tennis-data odds are (approx.) closing
  source text, source_row text,
  PK (match_id, bookmaker)
)
player_aliases(alias text, tour text, player_id int FK, PK (alias, tour))
edition_aliases(alias text, season int, tour text, edition_id text FK, PK(alias, season, tour))
ingest_log(id bigserial PK, run_at timestamptz, step text, stats jsonb)

-- 003_views.sql
-- modeling view: deterministic pseudo-random p1/p2 assignment (e.g. by hash(match_id) % 2)
CREATE VIEW tennis.matches_model AS SELECT ..., p1_id, p2_id, p1_won, ...;
-- market view: implied probs with proportional vig removal per bookmaker
CREATE VIEW tennis.odds_implied AS SELECT ..., 1/winner_odds AS raw_w, ...,
       (1/winner_odds)/(1/winner_odds + 1/loser_odds) AS p_winner_novig, ...,
       (1/winner_odds + 1/loser_odds - 1) AS overround, ...;
```

2. Supabase: the agent cannot create the cloud project itself — **the user must create
   a (free-tier) Supabase project once** and put `SUPABASE_DB_URL` (the Postgres
   connection string) into `.env`. Everything else is automated.
   Until those credentials exist, **all milestones proceed against DuckDB**, and
   `scripts/publish.py` (M5) is the only step that hard-requires Supabase.
3. Migration runner `scripts/migrate.py` applies `db/migrations/*.sql` in order to
   **both** targets: the DuckDB warehouse (schema-compatible subset) and, when
   configured, Supabase. Re-running is a no-op.

**Verify (M3)**
- `uv run python scripts/migrate.py --target duckdb` twice → second run reports
  "0 changes" (idempotent).
- With Supabase configured: same against `--target supabase`; then
  `select count(*) from information_schema.tables where table_schema='tennis'`
  returns the expected table count.
- `uv run pytest -m m3` checks constraints fire (inserting an odds row with unknown
  match_id fails; odds ≤ 1.0 rejected by CHECK).

---

## M4 — Entity resolution & merge (the core, highest-risk milestone)

Match every tennis-data row (which has odds) to its canonical Sackmann match.

**Tasks**
1. `resolve/players.py`: map tennis-data names (`"Federer R."`) to Sackmann player IDs:
   - exact match on `last_name + ' ' + first_initial.'` after unicode/diacritic folding;
   - fall back to rapidfuzz similarity ≥ threshold **within the same tour**, tie-broken
     by ranking proximity (tennis-data `WRank/LRank` vs Sackmann ranks that week);
   - unresolved names go to `player_aliases` candidates for review; ship a curated
     seed alias file in-repo (`db/seed/player_aliases.csv`) for known hard cases
     (e.g. "De Minaur A.", "Auger-Aliassime F.", Korean/Chinese name orderings).
2. `resolve/tournaments.py`: map (tennis-data `Tournament`, `Location`, season, tour) →
   Sackmann `edition_id` using name similarity + date overlap; persist to `edition_aliases`.
3. `resolve/matches.py`: join on (edition, both player IDs, round) with a ±3-day date
   tolerance; require the winner sides to agree; unresolved rows written to
   `data/quality/unmatched_odds.csv` with a reason code
   (`player_unresolved | edition_unresolved | no_candidate | ambiguous | winner_mismatch`).
4. Produce `tennis.odds` rows (long format: one row per match × bookmaker for
   B365, PS, Max, Avg where present).
5. A small **manual-review loop**: script prints top-50 unmatched by frequency; fixes go
   into the seed alias CSVs (committed), then resolution re-runs. Budget 2–3 iterations.

**Verify (M4)** — `uv run pytest -m m4`, which asserts on the built warehouse:
- **Match rate ≥ 97%** of tennis-data rows for seasons 2010+, **≥ 93%** overall
  (report printed per season × tour; failures list top unmatched examples).
- **Zero** matches with two different tennis-data rows mapped to them (uniqueness).
- **Winner agreement is 100%** on resolved rows (the sources must agree on who won —
  disagreement means a bad join, not a data fact).
- Spot-check fixtures: ~20 hand-written known matches (e.g. 2019 Wimbledon final:
  Djokovic d. Federer, B365 odds present) resolve to the correct `match_id` — encoded
  as a pytest fixture table.
- Rank cross-check: where both sources report ranks, they agree within ±2 on ≥ 95%
  of resolved rows (ranking snapshots differ by a few days — perfect equality is wrong
  as a target).

---

## M5 — Data-quality suite & publish to Supabase

**Tasks**
1. `quality/checks.py`: a declarative list of checks producing one JSON report
   (each check: name, scope, pass/fail, offending sample). Core checks:
   - no duplicate matches (same edition, players, round);
   - every match's winner_id ≠ loser_id; both players exist;
   - dates within edition window; `best_of ∈ {3,5}`; scores parse or carry
     retirement/walkover flag;
   - odds sanity: overround per bookmaker in **(0%, 15%)** for ≥ 99% of pairs;
     `Max ≥ Avg` odds on ≥ 99% of rows;
   - **favorite (by Avg odds) wins 62–70% of matches** — the single best global
     integrity check of the merge;
   - bookmaker margin trend: Pinnacle mean overround < Bet365 mean overround.
2. `load/supabase.py` + `scripts/publish.py`: bulk-upsert canonical tables
   (players, tournament_editions, matches, match_stats, rankings, odds, aliases) from
   DuckDB to Supabase via `psycopg` COPY (not the REST API — far faster), wrapped in a
   transaction per table, with row-count reconciliation written to `ingest_log`.

**Verify (M5)**
- `uv run python scripts/build_db.py --all && uv run pytest -m m5`:
  quality report has **0 failing checks** (or documented waivers in `quality/waivers.yaml`).
- After `scripts/publish.py`: row counts in Supabase equal DuckDB counts for every
  table (the script itself asserts this and exits non-zero on mismatch).
- From the Supabase SQL editor, this query returns plausible numbers
  (favorite win rate 62–70%, mean overround 2–9%):
  ```sql
  select avg((p_winner_novig > 0.5)::int) fav_win, avg(overround) from tennis.odds_implied where bookmaker='Avg';
  ```

---

## M6 — Feature layer (ratings & market features)

**Tasks**
1. `features/elo.py`: incremental Elo computed **chronologically** over `matches`:
   overall Elo + surface-specific Elo, K decaying with match count, new players at 1500.
   Output table `analytics.elo_pre` — the rating of both players **before** each match.
2. `features/form.py`: pre-match rolling features (win% last 10/25, days since last
   match, matches last 14 days, head-to-head record, age at match).
3. `features/market.py`: per-match market features from odds (novig closing prob,
   overround, Max/Avg dispersion as a liquidity/disagreement proxy).
4. All feature tables keyed by `match_id` and built by one command
   (`scripts/build_db.py --features`), with an explicit "as-of" discipline: any feature
   for match m may only read matches with `match_date < m.match_date`
   (enforced in code and asserted in tests via a shuffled-recompute check).
5. Because this repo is named *tennis-astrology*: add `features/astro.py` deriving
   zodiac sign / birth-date features from player DOB — cheap to build on top of the
   players table and a perfect **null-hypothesis demonstrator** for M8.

**Verify (M6)** — `uv run pytest -m m6`:
- Elo sanity: among 2015–2019 ATP season-end top-5 by Elo, we find Djokovic, Federer,
  Nadal, Murray in their expected eras (fixture list).
- **Predictive floor**: picking the higher pre-match Elo wins **≥ 63%** of ATP main-tour
  matches 2010–2019; higher official rank alone lands 60–64%; Elo ≥ rank baseline.
- Market beats models: closing novig favorite accuracy **>** Elo accuracy on the same
  matches (if not, the merge or the as-of discipline is broken — this is a canary, not
  a disappointment).
- Lookahead check: recomputing features with future rows withheld reproduces identical
  values for a random sample of 1,000 matches.

---

## M7 — Backtesting engine (financial-markets framing)

**Tasks**
1. `backtest/engine.py`: event-driven walk-forward loop:
   - iterate matches in strict chronological order;
   - a `Strategy` sees only (features, odds available pre-match) and returns
     `Bet(side, stake_fraction) | None`;
   - fills at chosen bookmaker's odds (default: Pinnacle if present else Avg;
     configurable slippage haircut, e.g. price × (1 − 0.01));
   - bankroll accounting, one pass = one equity curve.
2. `backtest/staking.py`: flat stake, fixed fraction, fractional Kelly (capped).
3. `backtest/metrics.py`: total ROI, annualized return, max drawdown, hit rate,
   average odds taken, **CLV** (bet price vs closing novig price), Brier/log-loss for
   probability models, and **bootstrap 95% CIs on ROI** (resample bets) plus a
   Monte-Carlo bankroll-ruin estimate.
4. `backtest/strategies/`: `base.py` + three reference strategies:
   - `RandomBet` (control — must lose ≈ the vig),
   - `BackFavorites` / `BackUnderdogs` (classic benchmarks),
   - `EloValue` (bet when Elo prob exceeds novig market prob by a margin θ).
5. `scripts/run_backtest.py --strategy elo_value --from 2015 --to 2019 --stake kelly:0.25`
   → prints metric table + writes equity curve CSV/PNG to `data/backtests/`.
6. Train/validation/test split discipline documented in the README: tune θ etc. only
   on ≤ 2018, keep 2019+ untouched until final evaluation (backtesting's version of
   out-of-sample; prevents the p-hacking that kills most betting "edges").

**Verify (M7)** — `uv run pytest -m m7`:
- **Synthetic-truth test**: on a constructed dataset with known probabilities and odds,
  the engine's ROI matches the closed-form expectation within 0.5% — proves the
  accounting is right.
- `RandomBet` on real ATP 2010–2019 Avg odds: ROI in **[−9%, −2%]** (≈ −vig),
  CLV ≈ 0.
- `BackFavorites` ROI negative but > `BackUnderdogs` ROI variance; both consistent
  with published stylized facts (favorite–longshot bias: underdogs lose more per unit).
- No-lookahead test: shifting all features forward by one match materially degrades
  `EloValue` (if it doesn't, information isn't flowing from features at all).
- Kelly staking never bets > cap, bankroll never goes negative.

---

## M8 — Hypothesis-research workflow (the deliverable the user actually wants)

**Tasks**
1. `docs/hypothesis_template.md`: a short protocol every idea follows —
   hypothesis → economic rationale → feature spec → in-sample period → pre-registered
   metric & threshold → out-of-sample result → verdict. One markdown file per study in
   `studies/`.
2. Implement three worked example studies end-to-end to prove the pipeline:
   - **S1 (market microstructure)**: does positive CLV persist for `EloValue` bets even
     when ROI is noisy? (CLV is the sharper edge detector.)
   - **S2 (behavioral)**: favorite–longshot bias by surface and odds bucket — where is
     the vig-adjusted expected value least negative?
   - **S3 (astrology, given the repo name — and a deliberate multiple-testing lesson)**:
     zodiac-sign features vs outcomes with proper Bonferroni/FDR correction; expected
     verdict: null. Demonstrates that the harness rejects spurious signals rather than
     confirming them.
3. `README.md` final rewrite: quickstart (env → ingest → build → publish → backtest),
   data licenses/attribution (Sackmann CC BY-NC-SA; tennis-data.co.uk personal use),
   and a "how to add a strategy / study" guide.
4. Optional automation (only if user wants it): a weekly script or GitHub Action that
   pulls new Sackmann commits + the current tennis-data season file, re-runs
   build+quality+publish, and appends to `ingest_log`.

**Verify (M8)**
- `uv run pytest` (full suite, all markers) green.
- Three study files exist with filled-in results tables generated by
  `scripts/run_backtest.py` / a `scripts/run_study.py` runner (numbers reproducible
  from a clean `build_db.py --all`).
- S3 reports corrected p-values > 0.05 (or honestly reports otherwise — the point is
  the protocol runs, not the outcome).
- A fresh clone + `.env` + the README quickstart reproduces the whole thing —
  final end-to-end check.

---

## Risks & fallbacks

| Risk | Mitigation |
|---|---|
| tennis-data.co.uk URL patterns / file formats drift by year | M1 reads the site's per-year index pages; per-year format quirks are absorbed in M2's union logic; manifest checksums detect silent changes |
| Entity resolution below target match rate | The M4 review loop + committed alias seed files; thresholds are per-era (older seasons are allowed to be worse) |
| Supabase free-tier limits (500 MB) | Core tables (~350k matches + ~250k odds rows) fit comfortably; `match_stats` and rankings can stay DuckDB-only if space gets tight |
| Sources disagree on facts (winner, ranks) | Sackmann wins by decision #3; disagreements are quality-report items, never silent overwrites |
| Backtest overfitting | Held-out final years (M7 task 6), pre-registration template, bootstrap CIs, CLV as primary edge metric |
| Odds are closing-only (no open/line movement) | Documented limitation; extension: Betfair historical exchange data or an odds API for live line capture (out of scope for core build) |

## Suggested implementation order & effort

M0 → M1 → M2 (mechanical, ~1 session) → M3 (needs the user's one-time Supabase project
creation, but DuckDB path unblocks everything) → **M4 (the big one — budget the most
iteration here)** → M5 → M6 → M7 → M8. Every milestone ends with a commit
`mX: <summary>` and a green `pytest -m mX`.
