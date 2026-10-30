"""Phase 3.4: time-matched random controls and multi-window diagnostics.

Predeclared price rule, no model tuning. Historical close-only research, not
transaction-executable quotes, option P&L, causal inference or verified alpha.
"""
from __future__ import annotations
import random
from statistics import median
try:
    from scripts.ai_rebound_study import scan_dislocations, first_passage
except ModuleNotFoundError:
    from ai_rebound_study import scan_dislocations, first_passage

WINDOW_YEARS = (2, 3, 5, 10, 15)
TRADING_DAYS = 252
HORIZON = 30
MIN_EVENTS = 5
SEED = 3419
CONTROL_DRAWS = 100
ROUNDTRIP_COST_PCT = 0.20


def trade_outcome(closes, signal_index, profit=10, stop=-10, cost=ROUNDTRIP_COST_PCT):
    """Signal only known after close: enter next close, then assess 30 closes."""
    entry_index = signal_index + 1
    if entry_index + HORIZON >= len(closes):
        raise ValueError("unresolved 30-session exit")
    status, offset = first_passage(closes, entry_index, HORIZON, profit, stop)
    exit_index = entry_index + (offset if offset is not None else HORIZON)
    net_return = 100 * (closes[exit_index] / closes[entry_index] - 1) - cost
    mae = 100 * (min(closes[entry_index+1:exit_index+1]) / closes[entry_index] - 1)
    return {"outcome": status, "net_return_pct": net_return,
            "mae_pct": mae, "sessions": exit_index - entry_index}


def _summarize(closes, entries):
    results = [trade_outcome(closes, i) for i in entries]
    return {"n": len(results),
            "mean_net_return_pct": round(sum(x["net_return_pct"] for x in results)/len(results), 2),
            "median_net_return_pct": round(median(x["net_return_pct"] for x in results), 2),
            "profit_first_pct": round(100 * sum(x["outcome"] == "profit" for x in results)/len(results), 1),
            "stop_first_pct": round(100 * sum(x["outcome"] == "stop" for x in results)/len(results), 1),
            "median_mae_pct": round(median(x["mae_pct"] for x in results), 2),
            "median_sessions_held": round(median(x["sessions"] for x in results), 1)}


def matched_controls(closes, signals, seed=SEED, draws=CONTROL_DRAWS, radius=63):
    """Random pseudo-entries from each signal's ±63-session neighborhood.

    Controls are not adjusted for the contemporaneous price-state; they estimate
    calendar-near unconditional entries, NOT isolated causal oversold effects.
    Sampling WITH replacement and repeated draws estimate baseline sensitivity.
    """
    last = len(closes) - HORIZON - 2
    rng = random.Random(seed)
    holdout_floor = max(251, len(closes) - 2 * TRADING_DAYS)
    pools = [list(range(max(holdout_floor, i-radius), min(last, i+radius)+1))
             for i in signals]
    if not pools or any(not p for p in pools):
        return []
    return [[rng.choice(p) for p in pools] for _ in range(draws)]


def edge_validation(closes, rsi_fn, min_events=MIN_EVENTS):
    """Fixed final two-year holdout; price rule is fixed, not fitted on test outcomes."""
    n = len(closes)
    out = {"status": "insufficient", "signal_n": 0, "holdout_bars": 0,
           "decision": "undetermined", "random_draws": CONTROL_DRAWS,
           "transaction_cost_pct": ROUNDTRIP_COST_PCT, "signal": {},
           "calendar_near_controls": {},
           "limitations": "Fixed predeclared rules; last 2y holdout; ±63-session calendar controls; noncausal, correlated and resampled; no IV/slippage/gaps; rule was proposed after inspecting market patterns"}
    if n < 252 + 3 * TRADING_DAYS + HORIZON + 2:
        return out
    holdout_start = n - 2 * TRADING_DAYS
    signals = [i for i in scan_dislocations(closes, rsi_fn)
               if i >= holdout_start and i+HORIZON+1 < n]
    out["holdout_bars"] = 2 * TRADING_DAYS
    out["signal_n"] = len(signals)
    if len(signals) < min_events:
        return out
    controls = matched_controls(closes, signals)
    if not controls:
        return out
    observed = _summarize(closes, signals)
    random_means = [_summarize(closes, draw)["mean_net_return_pct"] for draw in controls]
    random_wins = [_summarize(closes, draw)["profit_first_pct"] for draw in controls]
    differences = [observed["mean_net_return_pct"] - v for v in random_means]
    out["signal"] = observed
    out["calendar_near_controls"] = {
        "mean_net_return_median_pct": round(median(random_means), 2),
        "profit_first_median_pct": round(median(random_wins), 1),
        "signal_minus_control_median_pp": round(median(differences), 2),
        "control_mean_p10_pct": round(sorted(random_means)[int((len(random_means)-1)*.1)], 2),
        "control_mean_p90_pct": round(sorted(random_means)[int((len(random_means)-1)*.9)], 2),
        "draws": len(controls)}
    out["status"] = "exploratory_holdout"
    return out


def adaptive_window_diagnostics(closes, rsi_fn, min_events=MIN_EVENTS):
    """Window robustness, not auto-optimization or formal OOS model selection."""
    n = len(closes)
    all_events = scan_dislocations(closes, rsi_fn)
    final_holdout_start = max(0, n - 2 * TRADING_DAYS)
    rows = {}
    for years in WINDOW_YEARS:
        start = max(0, final_holdout_start - years * TRADING_DAYS)
        training = [i for i in all_events if start <= i
                    and i + HORIZON + 1 < final_holdout_start]
        row = {"status": "insufficient", "events": len(training),
               "effective_start_bar": start,
               "years_requested": years,
               "pre_holdout_only": True}
        if len(training) >= min_events:
            row["status"] = "exploratory"
            row["trade_summary"] = _summarize(closes, training)
        rows[str(years)] = row
    return {"status": "descriptive_only", "windows": rows,
            "holdout_start_bar": final_holdout_start,
            "window_selection": "none", "decision": "undetermined",
            "limitations": "Historical windows are compared descriptively before a fixed final 2y holdout. Do not rank them by hindsight or claim an optimal window. A 2y pre-holdout window may be sparse; regime stability not established."}
