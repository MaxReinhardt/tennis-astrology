# Studies

One markdown file per study, following [the hypothesis protocol](../docs/hypothesis_template.md).
The text above each `## Results` heading is the pre-registration; everything between
`<!-- generated:results -->` markers is rewritten by the runner and must never be edited
by hand.

```bash
uv run python scripts/run_study.py --study all        # or s1_clv_persistence, ...
```

Outputs land in `results/<study_id>/` (`result.json`, `charts/*.png`) and `results/index.json`,
which the web UI reads.

## Adding a study

1. Create `src/tennisdb/research/studies/<id>.py` with a class exposing `study_id`, `title`,
   a complete `Hypothesis`, and `run(context) -> StudyResult`. Use only
   `context.backtests` (any `BacktestRequest`) and `context.cross_section` (market-relative
   cohort outcomes) — never import a database.
2. Register it in `STUDIES` in `src/tennisdb/research/studies/__init__.py`.
3. Add its verdict logic to `tests/test_m8_studies.py` against the fake context.
4. Run it; commit the generated document and `results/`.

New *strategies* go in `src/tennisdb/backtest/strategies/` plus one entry in `STRATEGIES`;
the request schema, the CLI, the API and the UI pick them up automatically.

| Study | Question | Verdict |
|---|---|---|
| `s1_clv_persistence` | Does EloValue beat the closing line beyond its fills? | see file |
| `s2_favourite_longshot` | Where is EV least negative by surface and price? | see file |
| `s3_zodiac_null` | Do zodiac signs beat the market (after correction)? | see file |
| `s4_host_nation` | Does backing or fading home-nation players pay? | see file |
