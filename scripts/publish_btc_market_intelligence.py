from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("apps/dge-dashboard/data/market-intelligence.json")

def get_json(url):
    req = Request(url, headers={"User-Agent": "Victor-Investment-OS"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode())

def pct(a, b):
    return (a / b - 1) * 100 if b else 0

def percentile(values, value):
    return round(100 * sum(v <= value for v in values) / len(values), 1) if values else None

def okx_derivatives():
    funding = get_json("https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=90")["data"]
    oi_now = get_json("https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP")["data"]
    funding = sorted(funding, key=lambda x: int(x["fundingTime"]))
    rates = [float(x.get("realizedRate") or x["fundingRate"]) * 100 for x in funding]
    current_oi = float(oi_now[0]["oiUsd"])
    return rates, [current_oi], "OKX Public API"

def bybit_derivatives():
    funding = get_json("https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=90")["result"]["list"]
    oi = get_json("https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=1d&limit=30")["result"]["list"]
    funding = sorted(funding, key=lambda x: int(x["fundingRateTimestamp"]))
    oi = sorted(oi, key=lambda x: int(x["timestamp"]))
    rates = [float(x["fundingRate"]) * 100 for x in funding]
    open_interest = [float(x["openInterest"]) for x in oi]
    return rates, open_interest, "Bybit Public API"

def binance_derivatives():
    funding = get_json("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=90")
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1d&limit=30")
    rates = [float(x["fundingRate"]) * 100 for x in funding]
    open_interest = [float(x["sumOpenInterest"]) for x in oi]
    return rates, open_interest, "Binance Public API"

def main():
    out = {"schema_version": "btc-market-intelligence-v2", "as_of": datetime.now(timezone.utc).isoformat(), "modules": {}, "history": {}}
    errors = []
    for provider in (okx_derivatives, bybit_derivatives, binance_derivatives):
        try:
            rates, open_interest, source = provider()
            oi7 = pct(open_interest[-1], open_interest[-8]) if len(open_interest) >= 8 else None
            f7 = sum(rates[-21:]) / min(21, len(rates))
            f30 = sum(rates) / len(rates)
            funding_percentile = percentile(rates, rates[-1])
            oi_percentile = percentile(open_interest, open_interest[-1]) if len(open_interest) >= 8 else None
            status = "FUNDING ONLY" if oi7 is None else "DELEVERAGING" if oi7 <= -5 else "CROWDED" if oi7 >= 10 and f7 > 0.02 else "NEUTRAL" if abs(oi7) < 5 and abs(f7) < 0.02 else "ACTIVE"
            print("DERIVATIVES_PROVIDER_OK", source, "funding_records=", len(rates), "oi_records=", len(open_interest), flush=True)
            out["modules"]["derivatives"] = {"status": status, "funding_7d_avg_pct": round(f7, 4), "funding_30d_avg_pct": round(f30, 4), "funding_30d_percentile": funding_percentile, "open_interest_7d_change_pct": round(oi7, 2) if oi7 is not None else None, "open_interest_30d_percentile": oi_percentile, "source": source}
            break
        except Exception as exc:
            message = provider.__name__ + ": " + type(exc).__name__ + ": " + str(exc)[:300]
            errors.append(message)
            print("DERIVATIVES_PROVIDER_FAIL", message, flush=True)
    else:
        print("DERIVATIVES_ALL_PROVIDERS_FAILED", " | ".join(errors), flush=True)
        out["modules"]["derivatives"] = {"status": "DATA PENDING", "error": " | ".join(errors), "providers_attempted": ["OKX Public API", "Bybit Public API", "Binance Public API"]}

    try:
        candles = sorted(get_json("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400"), key=lambda x: x[0])[-90:]
        closes = [float(x[4]) for x in candles]
        volumes = [float(x[5]) for x in candles]
        returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        rv7 = (sum(x*x for x in returns[-7:]) / 7) ** 0.5 * math.sqrt(365) * 100
        rv30 = (sum(x*x for x in returns[-30:]) / 30) ** 0.5 * math.sqrt(365) * 100
        volume_ratio = (sum(volumes[-7:]) / 7) / (sum(volumes[-30:]) / 30)
        drawdown = (closes[-1] / max(closes[-30:]) - 1) * 100
        price7 = pct(closes[-1], closes[-8])
        score = int(rv7 > rv30 * 1.25) + int(volume_ratio > 1.3) + int(drawdown < -10)
        status = ["LOW", "NORMAL", "ELEVATED", "EXTREME"][score]
        out["modules"]["stress"] = {"status": status, "btc_price_7d_change_pct": round(price7, 2), "realized_vol_7d_pct": round(rv7, 1), "realized_vol_30d_pct": round(rv30, 1), "volume_ratio": round(volume_ratio, 2), "drawdown_30d_pct": round(drawdown, 1), "source": "Coinbase Exchange public candles"}
    except Exception as exc:
        out["modules"]["stress"] = {"status": "DATA PENDING", "error": str(exc)[:100]}

    out["modules"]["capital_flow"] = {"status": "DATA PENDING", "note": "ETF flow source validation pending"}
    out["modules"]["liquidity"] = {"status": "DATA PENDING", "note": "Stablecoin time-series source validation pending"}
    out["modules"]["supply"] = {"status": "DATA PENDING", "note": "Reliable on-chain cohort source not yet integrated"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()