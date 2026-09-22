from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from pathlib import Path

from victor_investment_os.data.adapters.coinbase import CoinbaseExchangeAdapter
from victor_investment_os.engines.dynamic_game import DynamicGameEngine, DGEInput, FactorVector
from victor_investment_os.engines.dynamic_game.features import kaufman_efficiency, percentile_rank
from victor_investment_os.models import Asset, PlannedDataRequest

OUT=Path("apps/dge-dashboard/data/latest.json")
INTEL=Path("apps/dge-dashboard/data/market-intelligence.json")

def clip(x): return max(0.0,min(100.0,float(x)))
def scale(x,lo,hi):
    return clip(100*(x-lo)/(hi-lo)) if hi>lo else 50.0

def intelligence_factors():
    if not INTEL.exists():
        return 50.0, 50.0, "DATA PENDING", "DATA PENDING"
    data=json.loads(INTEL.read_text(encoding="utf-8"))
    modules=data.get("modules",{})
    flow=modules.get("capital_flow",{})
    deriv=modules.get("derivatives",{})
    flow_status=flow.get("status","DATA PENDING")
    deriv_status=deriv.get("status","DATA PENDING")
    if flow_status == "DATA PENDING" or flow.get("etf_flow_7d_usd_m") is None:
        F=50.0
    else:
        F=clip(50.0 + float(flow["etf_flow_7d_usd_m"]) / 25.0)
    if deriv_status == "DATA PENDING" or deriv.get("open_interest_7d_change_pct") is None:
        D=50.0
    else:
        oi7=float(deriv["open_interest_7d_change_pct"])
        funding=float(deriv.get("funding_7d_avg_pct") or 0.0)
        D=clip(50.0 + 1.5*oi7 + 500.0*max(funding,0.0))
    return F,D,flow_status,deriv_status

def realized_shock(rows):
    closes=[float(r["close"]) for r in rows]
    vols=[float(r["volume"]) for r in rows]
    returns=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))]
    latest=abs(returns[-1])
    hist=sorted(abs(x) for x in returns[-90:-1])
    rank=100.0*sum(x <= latest for x in hist)/len(hist) if hist else 0.0
    vol7=sum(vols[-7:])/7
    vol30=sum(vols[-30:])/30
    volume_ratio=vol7/vol30 if vol30 else 1.0
    score=0.0
    if rank >= 99.5: score=max(score,95)
    elif rank >= 99: score=max(score,85)
    elif rank >= 97.5: score=max(score,65)
    elif rank >= 95: score=max(score,45)
    if volume_ratio >= 2.5: score=max(score,85)
    elif volume_ratio >= 1.8: score=max(score,65)
    elif volume_ratio >= 1.3: score=max(score,40)
    return score,{"daily_abs_return_pct":round(latest*100,2),"return_abs_percentile":round(rank,1),"volume_7d_vs_30d":round(volume_ratio,2)}

def scheduled_macro_risk(now):
    # Public Federal Reserve FOMC calendar: extract scheduled meeting dates.
    # CPI/NFP can be added once a stable public machine-readable calendar is selected.
    try:
        req=Request("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",headers={"User-Agent":"Victor-Investment-OS"})
        html=urlopen(req,timeout=20).read().decode("utf-8",errors="ignore")
        import re
        months={"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,"July":7,"August":8,"September":9,"October":10,"November":11,"December":12}
        dates=[]
        for month,days,year in re.findall(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:-(\d{1,2}))?\s+(\d{4})',html):
            day=int(days)
            dt=datetime(int(year),months[month],day,18,0,tzinfo=timezone.utc)
            dates.append(dt)
        future=[d for d in dates if d >= now-timedelta(hours=12)]
        if not future: return 0.0,{"source":"Federal Reserve FOMC calendar","next_event":None}
        event=min(future,key=lambda d:abs((d-now).total_seconds()))
        hours=(event-now).total_seconds()/3600
        ah=abs(hours)
        risk=90 if ah<=6 else 65 if hours>0 and ah<=24 else 35 if hours>0 and ah<=72 else 25 if hours<0 and ah<=12 else 0
        return float(risk),{"source":"Federal Reserve FOMC calendar","next_event":event.isoformat(),"hours_to_event":round(hours,1)}
    except Exception as exc:
        return 0.0,{"source":"Federal Reserve FOMC calendar","error":str(exc)[:120]}

def main():
    now=datetime.now(timezone.utc)
    req=PlannedDataRequest(
        request_key="dge-btc-1d",asset=Asset("BTC-USD","CRYPTO","COINBASE","USD"),
        dataset_type="OHLCV",frequency="1d",lookback_days=180,minimum_observations=90,
        required_fields=frozenset({"timestamp","open","high","low","close","volume"}),
        max_age_seconds=172800,proxy_policy="DISALLOW",normalization="RAW",
        consumers=("dynamic-game-engine",),lookback_bars=180,
        requested_start_date=(now-timedelta(days=190)).isoformat(),
        requested_end_date=now.isoformat(),
    )
    ds=CoinbaseExchangeAdapter().retrieve(req)
    rows=ds.records
    if len(rows)<90: raise RuntimeError(f"Need >=90 daily candles, got {len(rows)}")
    closes=[r["close"] for r in rows]; vols=[r["volume"] for r in rows]
    rets=[closes[i]/closes[i-1]-1 for i in range(1,len(closes))]
    er=kaufman_efficiency(closes,14)
    vol20=(sum(x*x for x in rets[-20:])/20)**0.5
    volume_rank=percentile_rank(vols[-1],vols[-90:])
    mom14=closes[-1]/closes[-15]-1
    range_pos=(closes[-1]-min(closes[-30:]))/(max(closes[-30:])-min(closes[-30:]) or 1)
    F,D,flow_status,deriv_status=intelligence_factors()
    market_shock,shock_detail=realized_shock(rows)
    scheduled_risk,scheduled_detail=scheduled_macro_risk(now)
    E=max(market_shock,scheduled_risk)
    # Live market factors plus Market Intelligence F/D. Missing C/E stay neutral (50), never fabricated.
    factors=FactorVector(
        R=clip(50+50*er*(1 if mom14>=0 else -1)),
        L=clip(35+45*volume_rank),
        F=F,C=50,
        P=clip(100*range_pos),
        V=clip(50+250*mom14),
        D=D,E=E,
        T=clip(100*(1-min(abs(mom14),.20)/.20)),
    )
    obs={"reclaim":max(-1,min(1,mom14*5)),"spot_cvd":0,"oi_flush":0,"supply_pressure":0,"capital_efficiency":0,"shock":max(-1.0,min(1.0,E/100.0))}
    out=DynamicGameEngine().analyze(DGEInput(
        symbol="BTC-USD",as_of=now.isoformat(),factors=factors,observations=obs,
        provenance={"OHLCV":ds.provenance.source_name,"F":"Market Intelligence / Farside ETF flows","D":"Market Intelligence / derivatives router","E":"Event Shock V1 / FOMC + realized BTC shock","C":"UNAVAILABLE_NEUTRAL_50"},
    )).to_dict()
    out["price"]=closes[-1]
    out["data_mode"]="PARTIAL_LIVE"
    out["live_factors"]=["R","L","F","P","V","D","E","T"]
    out["neutral_placeholders"]=["C"]
    out["factor_status"]={"F":flow_status,"D":deriv_status,"C":"DATA PENDING","E":"LIVE"}
    out["event_shock"]={"score":round(E,1),"scheduled_macro":scheduled_detail,"realized_market":shock_detail,"rule":"max(scheduled_macro_risk, realized_market_shock)"}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"price":out["price"],"state":out["dominant_state"],"confidence":out["confidence"],"rows":len(rows)}))
if __name__=="__main__": main()
