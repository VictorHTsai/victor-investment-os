# Signal research methodology

Separate **oversold**, **fundamental resilience**, and **conditional asymmetric return**. Never treat a low RSI alone as an entry recommendation.

Oversold candidates: 252-session peak-to-close drawdown, RSI(14), close/200-session MA, 20/60-session volatility-adjusted returns, and benchmark-relative weakness. Use historical percentile ranks computed only with information available by each evaluation date. Thresholds must be estimated in training windows and frozen for evaluation.

Analogs: define independent event clusters with a cooldown, use adjusted prices, compare 30/60/90 trading-day forward returns versus QQQ and sector proxy, report N, median, mean, positive rate, 10th percentile, max adverse excursion and bootstrap uncertainty. Avoid overlapping outcomes and survivorship bias. Exclude signals with insufficient observations.

Sector gates: AI Compute (customer CapEx, EPS revisions), Foundry (utilization and capital intensity), Equipment (orders/backlog), Memory (cycle-normalized EPS, inventory and pricing), Platforms (FCF/share and CapEx/OCF), Infrastructure (debt maturity and liquidity). Historical point-in-time fundamentals must be sourced before claiming these gates are passed.

All missing, stale, or unverified fields must be null/N/A, never zero or a fabricated score. No trading execution in Phase 1.
