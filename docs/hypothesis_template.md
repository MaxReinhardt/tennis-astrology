# Hypothesis protocol

Every betting idea is a *study*: a short, pre-registered document plus a runner that
fills in its numbers. Backtests are cheap, so the discipline is in what you fix **before**
you look. Copy this template into `studies/<id>.md`, or let `scripts/run_study.py`
scaffold it from the study's `Hypothesis`.

1. **Hypothesis** — one falsifiable sentence. *"Home-nation players win more often than
   their market price implies."* Not *"find edges in home-nation matches."*
2. **Economic rationale** — who is on the other side of the bet, and why would they be
   wrong? If there is no mechanism (e.g. zodiac signs), say so: the study becomes a null
   demonstrator and the expected verdict is rejection.
3. **Feature specification** — exactly which columns, as known strictly **before** the
   match starts. Features may only read matches with an earlier date.
4. **In-sample period** — the seasons you may look at and tune on (default: ≤ 2018).
5. **Pre-registered metric and threshold** — the decision rule, written as a test that can
   fail: *"Supported iff the 2019+ ROI 95% CI lies entirely above 0 with ≥ 100 bets."*
   Name the control that must be beaten (e.g. a `random_bet` run with identical fills).
6. **Out-of-sample result** — seasons ≥ 2019, touched once with the parameters fixed in
   step 4. Report ROI, CLV and their bootstrap intervals, never the point estimate alone.
7. **Verdict** — `supported`, `not_supported` or `inconclusive`, with one sentence of why.

## Rules that keep it honest

- **Correct for every test you ran**, not just the one that worked: Bonferroni or
  Benjamini–Hochberg across all cohorts examined (`research/significance.py`).
- **Beat the control, not zero.** CLV and ROI are measured net of slippage against the same
  fills a coin flip would get; a result that a `random_bet` run reproduces is not an edge.
- **Odds here are closing prices only.** There is no opening line, so CLV compares one
  book's close with another's — useful as a relative measure, never as proof of foresight.
- **One look at the holdout.** If you change the idea after seeing 2019+, it is a new study
  and the holdout is spent.
