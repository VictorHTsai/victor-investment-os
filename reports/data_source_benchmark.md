# Victor Investment OS — Data Source Benchmark

Analysis as of: `2026-09-10T00:00:00+00:00`
Comparison period: `2021-09-09` through `2026-09-09`

## Source availability

| Source | Tested | Credentials | Feed | Status |
|---|---:|---:|---|---|
| Alpaca | False | False | IEX (production adapter request) | NOT_TESTED_CREDENTIALS_UNAVAILABLE |
| Tiingo | False | False | EOD composite | NOT_TESTED_CREDENTIALS_UNAVAILABLE |
| Yahoo | True | False | structured chart JSON | AVAILABLE |

## Price semantics

| Source | Open / High / Low / Close | Adjusted close | Volume | Benchmark policy |
|---|---|---|---|---|
| Alpaca | API bar fields under `adjustment=all` | No separate field | Requested feed's bar volume | Existing adapter requests split/dividend-adjusted IEX bars |
| Tiingo | Raw and adjusted fields are separate | `adjClose` | Raw and `adjVolume` | Use adjusted OHLC and adjusted volume |
| Yahoo | Raw OHLC plus separate adjusted close | `adjclose` | Supplied volume | Reconstruct adjusted OHLC using `adjclose/close`; preserve volume |


## Data comparison

| Asset | Source | Bars | Coverage | Adjustment | Volume |
|---|---|---:|---|---|---|
| SLV | yahoo | 1254 | 2021-09-09 → 2026-09-08 | PROVIDER_ADJUSTED | AVAILABLE |
| AAPL | yahoo | 1254 | 2021-09-09 → 2026-09-08 | PROVIDER_ADJUSTED | AVAILABLE |
| QQQ | yahoo | 1254 | 2021-09-09 → 2026-09-08 | PROVIDER_ADJUSTED | AVAILABLE |

All completed datasets had zero duplicate trading dates. Source-only and missing-relative-to-other-source counts are `N/A` when only one source completed.

## OHLCV differences

No pairwise OHLCV statistics could be calculated because only Yahoo completed.

## Representative Compression V1 outputs

Percentiles below are compression percentiles except Volume Activity, which uses its contextual raw percentile.

| Asset | Source | Feature | Window | Raw value | 3Y percentile | 5Y percentile |
|---|---|---|---:|---:|---:|---:|
| SLV | yahoo | BBW | 20 | 0.10720439 | 0.665779 | 0.651515 |
| SLV | yahoo | ATR% | 20 | 0.02927405 | 0.290280 | 0.187400 |
| SLV | yahoo | RV | 20 | 0.36112788 | 0.338216 | 0.224880 |
| SLV | yahoo | Range% | 20 | 0.11925212 | 0.619174 | 0.567783 |
| SLV | yahoo | Volume Activity | 60 | 0.94633846 | 0.430093 | 0.433014 |
| AAPL | yahoo | BBW | 20 | 0.09196528 | 0.595206 | 0.638756 |
| AAPL | yahoo | ATR% | 20 | 0.02118304 | 0.443409 | 0.522329 |
| AAPL | yahoo | RV | 20 | 0.20521300 | 0.593875 | 0.665072 |
| AAPL | yahoo | Range% | 20 | 0.09562959 | 0.591212 | 0.639553 |
| AAPL | yahoo | Volume Activity | 60 | 0.73390761 | 0.007989 | 0.004785 |
| QQQ | yahoo | BBW | 20 | 0.04024249 | 0.880160 | 0.919458 |
| QQQ | yahoo | ATR% | 20 | 0.01115110 | 0.876165 | 0.912281 |
| QQQ | yahoo | RV | 20 | 0.12504031 | 0.837550 | 0.877193 |
| QQQ | yahoo | Range% | 20 | 0.04437887 | 0.896138 | 0.929825 |
| QQQ | yahoo | Volume Activity | 60 | 0.79916290 | 0.089214 | 0.057416 |

## Corporate-action spot check

- AAPL: AAPL's August 2020 four-for-one split predates the five-year comparison window. Cash dividends remain relevant, so provider dividend-adjustment methodology can still affect return and range continuity. Cross-provider behavior was not testable without authenticated Alpaca and Tiingo results.
- SLV / QQQ: ETF distributions make dividend-adjustment semantics relevant. Only Yahoo completed, so no provider-induced discontinuity comparison was possible.

## Maximum observed Compression difference

Not calculable. No feature had results from two or more sources, so assigning negligible/small/noticeable/large would be fabricated.

## Root cause

The missing comparison is caused by credential injection, not market data: the execution environment did not expose the required Alpaca or Tiingo variables. No numerical provider discrepancy can be attributed to corporate actions, OHLC construction, volume, missing bars, timestamps, or provider methodology from this run.

## Recommendation

**Interim: PRIMARY Alpaca → FALLBACK Yahoo. Do not add Tiingo to production routing yet.**

This preserves the existing route because the benchmark is inconclusive; it is not evidence that Alpaca outperformed Tiingo. Rerun after credentials are securely injected, then decide whether Tiingo earns the secondary position.

## Audit constraints

- Production routing was not changed.
- Compression Engine V1 methodology was not changed.
- Credentials are read only from environment variables.
- Missing authenticated sources are not inferred or fabricated.

## Documentation consulted

- [Alpaca Market Data API subscriptions](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [Tiingo End-of-Day API](https://www.tiingo.com/documentation/end-of-day)
- [Yahoo adjusted-close definition](https://help.yahoo.com/kb/SLN28256.html)
- [Apple's 2020 split announcement](https://www.apple.com/newsroom/2020/07/apple-reports-third-quarter-results/)
