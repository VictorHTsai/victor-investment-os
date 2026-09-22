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
    oi_history = get_json("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume?ccy=BTC&period=1D")["data"]
    funding = sorted(funding, key=lambda x: int(x["fundingTime"]))
    oi_history = sorted(oi_history, key=lambda x: int(x[0]))[-30:]
    rates = [float(x.get("realizedRate") or x["fundingRate"]) * 100 for x in funding]
    open_interest = [float(x[1]) for x in oi_history]
    if len(open_interest) < 8:
        raise ValueError("OKX historical OI returned fewer than 8 daily observations")
    return rates, open_interest, "OKX Public API"

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

def farside_etf_flows():
    from html.parser import HTMLParser
    class TableText(HTMLParser):
        def __init__(self):
            super().__init__(); self.rows=[]; self.row=[]; self.cell=[]; self.in_row=False; self.in_cell=False
        def handle_starttag(self, tag, attrs):
            if tag == "tr": self.in_row=True; self.row=[]
            if tag in ("td", "th") and self.in_row: self.in_cell=True; self.cell=[]
        def handle_data(self, data):
            if self.in_cell: self.cell.append(data)
        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.in_cell: self.row.append("".join(self.cell).strip()); self.in_cell=False
            if tag == "tr" and self.in_row: self.rows.append(self.row); self.in_row=False
    req = Request("https://farside.co.uk/btc/", headers={"User-Agent": "Mozilla/5.0 Victor-Investment-OS"})
    with urlopen(req, timeout=20) as response: html = response.read().decode("utf-8", errors="ignore")
    parser=TableText(); parser.feed(html); flows=[]
    for row in parser.rows:
        if len(row) < 2: continue
        try:
            datetime.strptime(row[0].strip(), "%d %b %Y")
        except ValueError: continue
        raw=row[-1].strip().replace(",", "")
        if raw in ("", "-"): continue
        negative=raw.startswith("(") and raw.endswith(")")
        raw=raw.strip("()")
        try: value=float(raw)
        except ValueError: continue
        flows.append((-value if negative else value))
    if len(flows) < 7: raise ValueError("Farside returned fewer than 7 daily ETF flow observations")
    return flows[-30:]

def defillama_stablecoin_liquidity():
    data = get_json("https://stablecoins.llama.fi/stablecoincharts/all")
    points = []
    for row in data:
        ts = int(row["date"])
        total = row.get("totalCirculatingUSD", {})
        value = total.get("peggedUSD") if isinstance(total, dict) else None
        if value is not None: points.append((ts, float(value)))
    points = sorted(points, key=lambda x: x[0])
    if len(points) < 91: raise ValueError("DefiLlama returned fewer than 91 stablecoin observations")
    values = [x[1] for x in points]
    current = values[-1]
    change7 = pct(current, values[-8])
    change30 = pct(current, values[-31])
    change90 = pct(current, values[-91])
    prior30 = pct(values[-31], values[-61])
    acceleration = change30 - prior30
    return current, change7, change30, change90, acceleration, len(values)

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
            status = "DELEVERAGING" if oi7 <= -5 else "CROWDED" if oi7 >= 10 and f7 > 0.02 else "NEUTRAL" if abs(oi7) < 5 and abs(f7) < 0.02 else "ACTIVE"
            print("DERIVATIVES_PROVIDER_OK", source, "funding_records=", len(rates), "oi_records=", len(open_interest), flush=True)
            out["modules"]["derivatives"] = {"status": status, "funding_7d_avg_pct": round(f7, 4), "funding_30d_avg_pct": round(f30, 4), "funding_30d_percentile": funding_percentile, "open_interest_7d_change_pct": round(oi7, 2), "open_interest_30d_percentile": oi_percentile, "source": source, "audit": {"oi_observations": len(open_interest), "oi_current": open_interest[-1], "oi_7d_ago": open_interest[-8], "oi_30d_min": min(open_interest), "oi_30d_max": max(open_interest), "current_equals_30d_max": open_interest[-1] == max(open_interest)}}
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

    try:
        etf = farside_etf_flows()
        flow7 = sum(etf[-7:])
        flow30 = sum(etf)
        positive_days = sum(x > 0 for x in etf[-7:])
        status = "POSITIVE" if flow7 > 250 and positive_days >= 4 else "NEGATIVE" if flow7 < -250 and positive_days <= 3 else "NEUTRAL"
        out["modules"]["capital_flow"] = {"status": status, "etf_flow_7d_usd_m": round(flow7, 1), "etf_flow_30d_usd_m": round(flow30, 1), "positive_days_7d": positive_days, "observations": len(etf), "source": "Farside Investors"}
        print("CAPITAL_FLOW_PROVIDER_OK", "Farside Investors", "records=", len(etf), flush=True)
    except Exception as exc:
        print("CAPITAL_FLOW_PROVIDER_FAIL", type(exc).__name__ + ": " + str(exc)[:300], flush=True)
        out["modules"]["capital_flow"] = {"status": "DATA PENDING", "error": str(exc)[:300], "source_attempted": "Farside Investors"}
    try:
        stable_supply, stable7, stable30, stable90, stable_accel, stable_records = defillama_stablecoin_liquidity()
        liquidity_status = "EXPANDING" if stable30 >= 2 and stable7 >= 0 else "CONTRACTING" if stable30 <= -2 else "STABLE"
        out["modules"]["liquidity"] = {"status": liquidity_status, "stablecoin_supply_usd_b": round(stable_supply / 1_000_000_000, 2), "stablecoin_supply_7d_change_pct": round(stable7, 2), "stablecoin_supply_30d_change_pct": round(stable30, 2), "stablecoin_supply_90d_change_pct": round(stable90, 2), "stablecoin_30d_acceleration_pp": round(stable_accel, 2), "source": "DefiLlama Stablecoins API"}
        print("LIQUIDITY_PROVIDER_OK", "DefiLlama Stablecoins API", "records=", stable_records, flush=True)
    except Exception as exc:
        print("LIQUIDITY_PROVIDER_FAIL", type(exc).__name__ + ": " + str(exc)[:300], flush=True)
        out["modules"]["liquidity"] = {"status": "DATA PENDING", "error": str(exc)[:300], "source_attempted": "DefiLlama Stablecoins API"}
    out["modules"]["supply"] = {"status": "DATA PENDING", "note": "Reliable on-chain cohort source not yet integrated"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()