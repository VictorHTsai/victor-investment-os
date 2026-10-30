#!/usr/bin/env python3
"""Produce an optional, provenance-labelled AI daily price snapshot.
Run from repo root: python -m scripts.build_ai_market_snapshot
No credentials. Yahoo Chart is an undocumented best-effort fallback, not an exchange feed.
"""
from __future__ import annotations
import json
import math
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
if __package__:
    from scripts.ai_analog_validation import selected_analog_indices, validate_analogs
    from scripts.ai_walkforward import walk_forward_diagnostic
    from scripts.ai_rebound_study import rebound_study
    from scripts.ai_price_volume_experiment import compare_price_volume
    from scripts.ai_edge_validation import edge_validation, adaptive_window_diagnostics
else:
    from ai_analog_validation import selected_analog_indices, validate_analogs
    from ai_walkforward import walk_forward_diagnostic
    from ai_rebound_study import rebound_study
    from ai_price_volume_experiment import compare_price_volume
    from ai_edge_validation import edge_validation, adaptive_window_diagnostics

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "apps/ai-dashboard/data/universe.json"
OUTPUT = ROOT / "apps/ai-dashboard/data/market-snapshot.json"

def rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) < n + 1: return None
    changes = [closes[i] - closes[i - 1] for i in range(len(closes)-n, len(closes))]
    gain = sum(max(x, 0) for x in changes) / n
    loss = sum(max(-x, 0) for x in changes) / n
    if gain == loss == 0: return 50.0
    if loss == 0: return 100.0
    return round(100 - 100 / (1 + gain / loss), 2)

def summarize(closes: list[float], dates: list[int]) -> dict:
    if len(closes) < 20: raise ValueError("fewer than 20 valid closes")
    latest = closes[-1]
    lookback = closes[-252:]
    high = max(lookback)
    drawdown = (latest / high - 1) * 100 if high else None
    return {"close": round(latest, 4), "currency": None,
            "last_bar_utc": datetime.fromtimestamp(dates[-1], timezone.utc).isoformat(),
            "bars": len(closes), "rsi14": rsi(closes),
            "drawdown_52w_pct": round(drawdown, 2) if drawdown is not None else None,
            "oversold_score": None, "analogs": None,
            "note": "RSI and 52-week drawdown are descriptive, not validated opportunity scores"}


def exploratory_analogs(closes: list[float], horizons=(30, 60, 90)) -> dict:
    """Historical matched-state descriptive study; not a predictive backtest.
    Select non-overlapping 90-session windows and exclude unresolved forward returns.
    Similarity uses RSI14 and trailing 252-close drawdown, both point-in-time.
    """
    from statistics import median
    n = len(closes)
    empty = {"status": "insufficient", "count": 0, "horizons": {},
             "method": "RSI14 ±10; 252-close drawdown ±10 percentage points; 90-session non-overlap"}
    if n < 252 + max(horizons) + 1:
        return empty
    target_rsi = rsi(closes)
    target_dd = 100 * (closes[-1] / max(closes[-252:]) - 1)
    selected = selected_analog_indices(closes, rsi, horizons)
    if len(selected) < 5:
        return {**empty, "count": len(selected)}
    results = {}
    for h in horizons:
        values = sorted(100 * (closes[i+h] / closes[i] - 1) for i in selected)
        k = len(values)
        results[str(h)] = {
            "median_pct": round(median(values), 2),
            "positive_pct": round(100 * sum(v > 0 for v in values) / k, 1),
            "p10_pct": round(values[int((k-1)*0.10)], 2),
            "p90_pct": round(values[int((k-1)*0.90)], 2),
        }
    return {"status": "exploratory", "count": len(selected), "horizons": results,
            "method": empty["method"],
            "limitations": "Five-year sample, current constituents, overlapping market regimes, selection bias; not out-of-sample validated"}

def validate_daily_cadence(dates: list[int]) -> None:
    if len(dates) < 20:
        raise ValueError(f"insufficient daily bars: {len(dates)}")
    gaps = sorted((dates[i] - dates[i-1]) / 86400 for i in range(1, len(dates)))
    median_gap = gaps[len(gaps)//2]
    if median_gap > 5:
        raise ValueError(f"daily frequency integrity failure: {len(dates)} bars; median gap {median_gap:.1f} days")


def fetch(symbol: str, benchmarks=None, return_history=False) -> dict:
    end_time = datetime.now(timezone.utc) + timedelta(days=1)
    start_time = end_time - timedelta(days=365 * 15 + 5)
    url = ("https://query2.finance.yahoo.com/v8/finance/chart/" + quote(symbol, safe="")
           + f"?period1={int(start_time.timestamp())}&period2={int(end_time.timestamp())}"
           + "&interval=1d&events=div%2Csplits&includeAdjustedClose=true")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 VictorInvestmentOS/1.0"})
    with urlopen(req, timeout=18) as resp:
        payload = json.load(resp)
    chart = payload.get("chart") or {}
    if chart.get("error"): raise ValueError(str(chart["error"]))
    result = (chart.get("result") or [None])[0]
    if not result: raise ValueError("no chart result")
    indicator = result.get("indicators") or {}
    quotes = (indicator.get("quote") or [{}])[0]
    adjusted = (indicator.get("adjclose") or [{}])[0].get("adjclose") or []
    raw = quotes.get("close") or []
    volume = quotes.get("volume") or []
    timestamps = result.get("timestamp") or []
    bars = [(t, float(adjusted[i] if i < len(adjusted) and adjusted[i] is not None else v),
             float(volume[i]) if i < len(volume) and volume[i] is not None and math.isfinite(float(volume[i])) and float(volume[i]) > 0 else None)
            for i, (t, v) in enumerate(zip(timestamps, raw))
            if v is not None and math.isfinite(float(v)) and float(v) > 0]
    if not bars: raise ValueError("no valid bars")
    # Keep up to 15 years; recent IPOs naturally have shorter trading histories.
    cutoff = max(t for t, _, _ in bars) - int(15 * 365.25 * 86400)
    bars = [(t, c, vol) for t, c, vol in bars if t >= cutoff]
    dates, closes, volumes = zip(*bars)
    # Reject silent monthly/weekly downsampling before computing daily indicators.
    validate_daily_cadence(list(dates))
    if return_history:
        return (list(dates), list(closes))
    summary = summarize(list(closes), list(dates))
    summary["currency"] = (result.get("meta") or {}).get("currency")
    summary["exploratory_analogs"] = exploratory_analogs(list(closes))
    summary["analog_validation"] = validate_analogs(list(closes), list(dates), benchmarks or {}, rsi)
    summary["chronological_holdout"] = walk_forward_diagnostic(list(closes))
    summary["short_rebound"] = rebound_study(list(closes), rsi)
    summary["price_volume_challenger"] = compare_price_volume(list(closes), list(volumes), rsi)
    summary["edge_controls"] = edge_validation(list(closes), rsi)
    summary["adaptive_windows"] = adaptive_window_diagnostics(list(closes), rsi)
    summary["historical_start_utc"] = datetime.fromtimestamp(dates[0], timezone.utc).isoformat()
    summary["price_type"] = "provider adjusted close where available; otherwise raw close"
    return summary

def main():
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    output = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "source": "Yahoo Finance Chart (undocumented, no-key, best effort)",
              "frequency": "1d", "history_limit_years": 15, "history_storage": "summary-only",
              "signals_validated": False, "volume_experiment": "price-only champion; high-RVOL challenger (research only)", "assets": {}}
    benchmark_histories = {}
    for name in ("QQQ", "SMH"):
        try:
            benchmark_histories[name] = fetch(name, return_history=True)
        except Exception as exc:
            print(f"Benchmark {name} unavailable: {str(exc)[:140]}")
    output["benchmark_alignment"] = "Exact UTC calendar-day entry and exit observations; no forward fill"
    output["benchmark_sources"] = list(benchmark_histories)
    for item in universe["assets"]:
        symbol = item["symbol"]
        try:
            output["assets"][symbol] = {"status": "ok", **fetch(symbol, benchmarks=benchmark_histories)}
        except Exception as exc:
            output["assets"][symbol] = {"status": "unavailable", "error": str(exc)[:180],
                                        "oversold_score": None, "analogs": None}
        time.sleep(0.2)
    ok = sum(v["status"] == "ok" for v in output["assets"].values())
    total = len(output["assets"])
    print(f"Snapshot: {ok}/{total} tickers, candidate for {OUTPUT}")
    # Fail closed: never replace a usable snapshot with broadly missing data.
    if ok < max(1, math.ceil(total * 0.8)) or not all(k in benchmark_histories for k in ("QQQ", "SMH")):
        raise SystemExit("Daily snapshot quality gate failed; previously published data preserved")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
