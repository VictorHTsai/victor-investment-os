"""Phase 3.3: exploratory short-horizon, close-only dislocation event study.

This is not an options backtest. Execution assumed at the signal close, ignoring
spread, fees, slippage, taxes and overnight gaps. Targets are observed at closes,
not intraday. Events are 30 trading sessions apart, not statistically independent.
"""
from __future__ import annotations
from statistics import median

HORIZONS = (5, 10, 20, 30)
TARGETS = (10, 15, 20)
MIN_EVENTS = 5


def _p10(values):
    v = sorted(values)
    return round(v[int((len(v) - 1) * 0.1)], 2)


def scan_dislocations(closes, rsi_fn, spacing=30):
    """Fixed, predeclared RSI <= 30 and trailing-252-day drawdown <= -15%."""
    events = []
    for i in range(251, len(closes) - max(HORIZONS)):
        rr = rsi_fn(closes[: i + 1])
        dd = 100 * (closes[i] / max(closes[i - 251:i + 1]) - 1)
        if rr is not None and rr <= 30 and dd <= -15:
            if not events or i - events[-1] >= spacing:
                events.append(i)
    return events


def first_passage(closes, start, horizon=30, profit_pct=10, stop_pct=-10):
    """First CLOSE crossing either barrier after entry, gap-order unambiguous."""
    entry = closes[start]
    for offset in range(1, horizon + 1):
        change = 100 * (closes[start + offset] / entry - 1)
        if change >= profit_pct:
            return "profit", offset
        if change <= stop_pct:
            return "stop", offset
    return "neither", None


def rebound_study(closes, rsi_fn, min_events=MIN_EVENTS):
    result = {
        "status": "insufficient", "count": 0, "horizons": {}, "targets": {},
        "rule": "RSI14 <= 30 AND 252-close drawdown <= -15%; 30-session spacing",
        "data_assumption": "adjusted daily closes only; target/stop evaluated at close; entry at signal close",
        "limitations": "in-sample, price-only, no trading costs, no options IV/theta, no fundamentals, no regime or survivorship control"
    }
    if len(closes) < 252 + max(HORIZONS) + 1:
        return result
    indices = scan_dislocations(closes, rsi_fn)
    result["count"] = len(indices)
    if len(indices) < min_events:
        return result
    for h in HORIZONS:
        returns = [100 * (closes[i+h] / closes[i] - 1) for i in indices]
        adverse = [100 * (min(closes[i+1:i+h+1]) / closes[i] - 1) for i in indices]
        result["horizons"][str(h)] = {
            "n": len(indices), "median_return_pct": round(median(returns), 2),
            "positive_pct": round(100 * sum(v > 0 for v in returns) / len(returns), 1),
            "p10_return_pct": _p10(returns),
            "median_mae_pct": round(median(adverse), 2),
            "p10_mae_pct": _p10(adverse),
        }
    for t in TARGETS:
        outcomes = [first_passage(closes, i, profit_pct=t) for i in indices]
        hits = [days for status, days in outcomes if status == "profit"]
        stops = sum(status == "stop" for status, _ in outcomes)
        result["targets"][str(t)] = {
            "profit_before_stop_pct": round(100 * len(hits) / len(indices), 1),
            "stop_before_profit_pct": round(100 * stops / len(indices), 1),
            "neither_pct": round(100 * (len(indices)-len(hits)-stops)/len(indices), 1),
            "median_days_to_profit": median(hits) if hits else None,
            "n": len(indices),
        }
    result["status"] = "exploratory"
    return result
