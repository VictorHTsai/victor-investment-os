"""Predeclared Price vs Price+Volume holdout challenger. No trading signals."""
from __future__ import annotations
import math
from statistics import median
from scripts.ai_rebound_study import scan_dislocations, first_passage

def relative_volume(volumes, index, length=20):
    """Current session volume vs prior 20 sessions; no current-bar denominator."""
    if index < length or index >= len(volumes):
        return None
    sample = volumes[index-length:index+1]
    if not all(v is not None and math.isfinite(v) and v > 0 for v in sample):
        return None
    return volumes[index] / (sum(sample[:-1]) / length)

def compare_price_volume(closes, volumes, rsi_fn, min_holdout=5):
    out = {
        "status": "insufficient", "price_only_n": 0, "price_volume_n": 0,
        "volume_available": False, "holdout": {}, "decision": "undetermined",
        "rules": {
            "price": "RSI14 <=30, 252-close drawdown <=-15%; 30-session spacing",
            "challenger": "same price events AND current-day volume / prior 20-day mean >=1.5",
            "split": "50% chronological split; 30-session embargo; 30-session outcome"
        },
        "caveats": "Single holdout; small correlated sample; in-sample hypothesis formation; no costs, slippage, intraday fills or option Greeks; adjusted close vs share volume requires corporate-action scrutiny"
    }
    if len(closes) != len(volumes) or len(closes) < 650:
        return out
    valid = sum(v is not None and math.isfinite(v) and v > 0 for v in volumes)
    out["volume_coverage_pct"] = round(100 * valid / len(volumes), 1)
    if valid / len(volumes) < 0.95:
        return out
    out["volume_available"] = True
    cutoff = len(closes) // 2
    events = scan_dislocations(closes, rsi_fn)
    price = [i for i in events if i >= cutoff + 30 and i + 30 < len(closes)]
    challenger = [i for i in price if (relative_volume(volumes, i) or 0) >= 1.5]
    out["price_only_n"] = len(price)
    out["price_volume_n"] = len(challenger)
    out["train_price_events"] = sum(i + 30 < cutoff for i in events)
    if len(price) < min_holdout or len(challenger) < min_holdout:
        return out

    def score(indices):
        outcomes = [first_passage(closes, i, horizon=30, profit_pct=10, stop_pct=-10) for i in indices]
        returns = [100 * (closes[i+20] / closes[i] - 1) for i in indices]
        adverse = [100 * (min(closes[i+1:i+31]) / closes[i] - 1) for i in indices]
        n = len(indices)
        return {
            "n": n,
            "profit_first_pct": round(100 * sum(o == "profit" for o, _ in outcomes) / n, 1),
            "stop_first_pct": round(100 * sum(o == "stop" for o, _ in outcomes) / n, 1),
            "median_20d_return_pct": round(median(returns), 2),
            "median_30d_mae_pct": round(median(adverse), 2)
        }
    base = score(price)
    extra = score(challenger)
    out["holdout"] = {
        "price_only": base, "price_volume": extra,
        "profit_first_difference_pp": round(extra["profit_first_pct"] - base["profit_first_pct"], 1),
        "median_20d_difference_pp": round(extra["median_20d_return_pct"] - base["median_20d_return_pct"], 2)
    }
    out["status"] = "exploratory_holdout"
    return out
