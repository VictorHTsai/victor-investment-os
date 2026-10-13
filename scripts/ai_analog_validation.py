"""Exploratory, date-aligned historical analog comparison — not investment signals."""
from __future__ import annotations
from datetime import datetime, timezone
from statistics import median

HORIZONS = (30, 60, 90)


def _percentile(values, q):
    """Empirical nearest-rank percentile; deliberately no interpolated precision."""
    ordered = sorted(values)
    return round(ordered[int((len(ordered) - 1) * q)], 2)


def selected_analog_indices(closes, rsi_fn, horizons=HORIZONS):
    """Point-in-time features only; do not use forward performance to select entries."""
    window = max(horizons)
    if len(closes) < 252 + window + 1:
        return []
    target_rsi = rsi_fn(closes)
    target_dd = 100 * (closes[-1] / max(closes[-252:]) - 1)
    selected = []
    # Prefix RSI uses only prices available as of historical sample date.
    for i in range(251, len(closes) - window):
        rr = rsi_fn(closes[:i + 1])
        dd = 100 * (closes[i] / max(closes[i - 251:i + 1]) - 1)
        if rr is not None and abs(rr - target_rsi) <= 10 and abs(dd - target_dd) <= 10:
            if not selected or i - selected[-1] >= window:
                selected.append(i)
    return selected


def validate_analogs(closes, dates, benchmark_histories, rsi_fn, min_samples=5):
    """Compare same historical entry and exit dates, without borrowing future quotes.

    Benchmarks are timestamp/close pairs. Exact UTC calendar-date alignment is required.
    This excludes holidays rather than substituting an unobserved quote.
    """
    selected = selected_analog_indices(closes, rsi_fn)
    output = {
        "status": "insufficient" if len(selected) < min_samples else "exploratory",
        "count": len(selected),
        "independence": "90-session entry spacing (not statistical independence)",
        "baseline": "same-date unconditional benchmark not yet computed",
        "horizons": {},
        "benchmarks": {},
        "limitations": "In-sample matches to today's regime; survivorship, secular trend, regime clustering, non-random entry choice; not causal alpha or out-of-sample validated",
    }
    if len(selected) < min_samples:
        return output
    for horizon in HORIZONS:
        vals = [100 * (closes[i + horizon] / closes[i] - 1) for i in selected]
        output["horizons"][str(horizon)] = {
            "n": len(vals), "median_pct": round(median(vals), 2),
            "positive_pct": round(100 * sum(v > 0 for v in vals) / len(vals), 1),
            "p10_pct": _percentile(vals, .10),
            "p90_pct": _percentile(vals, .90),
        }
    def calendar_date(ts):
        return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
    for symbol, history in benchmark_histories.items():
        bench_dates, bench_closes = history
        # Map exact dates, never forward-fill or nearest-future match.
        by_day = {calendar_date(t): price for t, price in zip(bench_dates, bench_closes)}
        horizons = {}
        for horizon in HORIZONS:
            excess, bench_returns = [], []
            for i in selected:
                entry = by_day.get(calendar_date(dates[i]))
                exit_ = by_day.get(calendar_date(dates[i + horizon]))
                if not entry or not exit_:
                    continue
                stock_return = 100 * (closes[i + horizon] / closes[i] - 1)
                bench_return = 100 * (exit_ / entry - 1)
                excess.append(stock_return - bench_return)
                bench_returns.append(bench_return)
            if len(excess) < min_samples:
                horizons[str(horizon)] = {"status": "insufficient", "n": len(excess)}
                continue
            horizons[str(horizon)] = {
                "status": "exploratory", "n": len(excess),
                "benchmark_median_pct": round(median(bench_returns), 2),
                "excess_median_pp": round(median(excess), 2),
                "outperform_pct": round(100 * sum(v > 0 for v in excess) / len(excess), 1),
                "excess_p10_pp": _percentile(excess, .10),
            }
        output["benchmarks"][symbol] = horizons
    return output
