# Victor × Andre Asymmetric Opportunity Radar — Phase 1

Independent additive prototype in `apps/asymmetric-opportunity/`. No existing engines, workflows, dashboards, contracts or configuration are modified. The interface deliberately displays N/A rather than invented trading metrics.

## Local preview

From repository root: `python -m http.server 8000` then open `http://localhost:8000/apps/asymmetric-opportunity/`.

## Next research milestones
1. Obtain licensed, split-adjusted daily OHLCV for every ticker and benchmarks (SOX proxy, QQQ), with exchange calendars and provenance.
2. Calculate rolling drawdown, RSI(14), moving-average deviation, volatility-normalized decline, and within-sector historical percentiles without lookahead.
3. Event-study 30/60/90 trading-day forward returns using nonoverlapping events, transaction costs, benchmark-adjusted results, tail losses, confidence intervals and out-of-sample splits.
4. Add sector-specific survivability and fundamental checks using point-in-time financial statements and estimates; block signals on stale or missing data.
5. Only then publish scored signals. Options remain out of scope.

## Data contract
`data/universe.json` contains research coverage, with all unverified metrics set to null. The web UI does not fetch external APIs or transmit information.
