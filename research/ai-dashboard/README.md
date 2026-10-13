# Victor AI Industry Dashboard — Phase 1A

Standalone module under Victor Investment OS. Future top-level overview can link to this module without changing its internals.

## Local preview

From repository root: `python -m http.server 8000` then open `http://localhost:8000/apps/ai-dashboard/`.

Five tabs: Overview, Opportunity Radar, Company Deep Dive, AI Industry Risk, Methodology.

The research universe is administrator-curated in `apps/ai-dashboard/data/universe.json`. Visitors can query a ticker once; the query is not stored, and non-covered symbols do not trigger backend work. No portfolio, accounts, or per-user persistence.

**No live feed or validated scores yet.** Next: historical price ingestion, point-in-time oversold metrics, conditional return backtesting, and quality gates. This directory is additive and does not replace or modify existing BTC/DGE dashboards.
