# Project Structure

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

# Coding Instructions

## Clean Code Rules

When writing or reviewing code, follow Clean Code principles:
- Use intention-revealing names; no abbreviations or cryptic identifiers.
- Keep functions small, single-purpose, and limited to 0-2 arguments.
- Prefer exceptions over error codes. Never return or pass null.
- Minimise comments — make code self-explanatory instead. Only comment on "why", never "what."
- Apply SRP to classes: one reason to change per class.
- Write clean, readable tests that cover happy paths, edge cases, and error paths.
- Delete dead code, commented-out code, and redundant comments.
- Leave every file you touch slightly cleaner than you found it.

## Testing Guidelines

Follow test-driven development: write a failing test before implementing any feature or bug fix (Red-Green-Refactor).

### Test pyramid
- Write many fast unit tests that assert behaviour (input → output), not implementation.
- Write focused integration tests for database queries, API boundaries, and external services.
- Write few E2E tests covering only critical user journeys.

### Rules
- Structure tests as Arrange-Act-Assert.
- Use stubs/fakes over mocks. Only mock when verifying an interaction is the point of the test.
- Each test is independent — no shared mutable state.
- Name tests descriptively: `test_<unit>_<scenario>_<expected_result>`.
- On bug fixes: write a failing regression test first, then fix.
- Delete flaky or low-value tests rather than skipping them.
- Do not aim for 100 % line coverage — aim for meaningful coverage of business-critical paths.

## Design Patterns

When implementing or suggesting design patterns, follow these guidelines:

- **Favor composition over inheritance.** Prefer patterns like Strategy, Decorator, and Bridge (which use composition) over Template Method or class-based Adapter (which rely on inheritance) unless there is a clear reason not to.
- **Don't over-engineer.** Only introduce a pattern when the problem actually calls for it. A simple function or class is better than a pattern applied prematurely.
- **Name things after the pattern.** If you use a pattern, reflect it in the naming: `OrderBuilder`, `PaymentStrategy`, `LoggingProxy`, `FileVisitor`. This makes intent immediately obvious.
- **Prefer Factory Method or Builder for object creation.** Avoid raw constructors with many parameters. Use Builder for complex objects with optional config; use Factory Method when subclasses need to control instantiation.
- **Use Singleton only for truly global, shared resources** (config, connection pools, loggers). Never use it as a shortcut for avoiding dependency injection.
- **Choose Strategy over switch/if-else chains.** When behavior varies by type or mode, extract each variant into a Strategy class instead of branching.
- **Choose State over status flags.** When an object's behavior depends on its internal state, use the State pattern rather than conditionals on a status field.
- **Use Observer/event systems for loose coupling.** When one change should notify multiple consumers, prefer Observer over direct method calls between unrelated classes.
- **Use Decorator to layer behavior, not subclassing.** When you need to combine optional behaviors (logging + caching + auth), stack Decorators instead of creating a subclass per combination.
- **Document the pattern in use.** Add a brief comment or docstring stating which pattern is being used and why, so future readers don't have to reverse-engineer the intent.

## Clean Architecture Rules

- All source code dependencies point inward: Frameworks → Adapters → Use Cases → Entities.
- Inner layers define interfaces; outer layers implement them. Use dependency injection.
- Entities contain only business rules — no framework imports.
- Use cases orchestrate one business action each. They call repository/gateway interfaces, never concrete implementations.
- Controllers and adapters handle data mapping (DTOs ↔ domain models) and input format validation.
- Business validation belongs in use cases; invariant enforcement belongs in entities.
- Organize code by feature first, then by layer within each feature.
- Folder structure should reflect domain concepts, not framework conventions.
- Never pass ORM entities or framework-specific types across layer boundaries.
- Keep interfaces small and focused on what the consumer actually needs.
- Test domain logic with pure unit tests, use cases with mocked dependencies, adapters with integration tests.
