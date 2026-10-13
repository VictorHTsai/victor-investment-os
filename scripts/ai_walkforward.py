"""Frozen-threshold chronological holdout diagnostics. Research only.

Train on the first 70% of bars; reserve a 90-bar embargo before the holdout.
Quantiles are fixed before observing holdout results. No strategy optimization.
"""
from __future__ import annotations
from statistics import median

HORIZONS = (30, 60, 90)


def historical_rsi(closes, end, period=14):
    if end < period:
        return None
    changes = [closes[j] - closes[j - 1] for j in range(end - period + 1, end + 1)]
    gain = sum(max(x, 0) for x in changes) / period
    loss = sum(max(-x, 0) for x in changes) / period
    if gain == loss == 0:
        return 50.0
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def _quantile(vals, fraction):
    vals = sorted(vals)
    return vals[int((len(vals) - 1) * fraction)]


def walk_forward_diagnostic(closes, min_events=5):
    n = len(closes)
    result = {"status": "insufficient", "train_bars": 0, "test_bars": 0,
              "signal_events": 0, "unconditional_events": 0, "horizons": {},
              "method": "Fixed train-70% thresholds; 90-bar embargo; chronological holdout; 90-bar entry spacing",
              "limitations": "Single holdout, only five years, sparse tail events, fixed current survivors; event selection may favor regimes; not independently validated"}
    if n < 252 + 90 + 252:
        return result
    cutoff = int(n * .70)
    holdout = cutoff + 90
    last_entry = n - max(HORIZONS) - 1
    if holdout > last_entry:
        return result
    train_rsi, train_dd = [], []
    for i in range(251, cutoff - 90):
        train_rsi.append(historical_rsi(closes, i))
        train_dd.append(100 * (closes[i] / max(closes[i - 251:i + 1]) - 1))
    if len(train_rsi) < 100:
        return result
    rsi_limit = _quantile(train_rsi, .30)
    drawdown_limit = _quantile(train_dd, .30)
    eligible = []
    for i in range(holdout, last_entry + 1):
        rr = historical_rsi(closes, i)
        dd = 100 * (closes[i] / max(closes[i - 251:i + 1]) - 1)
        if rr <= rsi_limit and dd <= drawdown_limit:
            eligible.append(i)
    chosen = []
    for i in eligible:
        if not chosen or i - chosen[-1] >= 90:
            chosen.append(i)
    # Unconditional comparison uses a fixed schedule, not selected on future performance.
    baseline = list(range(holdout, last_entry + 1, 90))
    result.update({"train_bars": cutoff - 90, "test_bars": n - holdout,
                   "signal_events": len(chosen), "unconditional_events": len(baseline),
                   "frozen_thresholds": {"rsi14_max": round(rsi_limit, 2),
                                         "drawdown_52w_max_pct": round(drawdown_limit, 2)}})
    if len(chosen) < min_events or len(baseline) < min_events:
        return result
    for h in HORIZONS:
        signals = [100 * (closes[i+h] / closes[i] - 1) for i in chosen]
        controls = [100 * (closes[i+h] / closes[i] - 1) for i in baseline]
        result["horizons"][str(h)] = {
            "signal_median_pct": round(median(signals), 2),
            "baseline_median_pct": round(median(controls), 2),
            "median_difference_pp": round(median(signals) - median(controls), 2),
            "signal_positive_pct": round(100 * sum(x > 0 for x in signals) / len(signals), 1),
            "signal_p10_pct": round(_quantile(signals, .10), 2),
            "baseline_p10_pct": round(_quantile(controls, .10), 2),
        }
    result["status"] = "exploratory_holdout"
    return result
