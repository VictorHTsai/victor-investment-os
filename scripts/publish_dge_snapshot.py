from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from victor_investment_os.data.adapters.coinbase import CoinbaseExchangeAdapter
from victor_investment_os.engines.dynamic_game import DynamicGameEngine, DGEInput, FactorVector
from victor_investment_os.engines.dynamic_game.features import kaufman_efficiency, percentile_rank
from victor_investment_os.models import Asset, PlannedDataRequest

OUT=Path("apps/dge-dashboard/data/latest.json")

def clip(x): return max(0.0,min(100.0,float(x)))
def scale(x,lo,hi):
    return clip(100*(x-lo)/(hi-lo)) if hi>lo else 50.0

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
    # Phase-1 market-only factors. Missing external datasets stay neutral (50), never fabricated.
    factors=FactorVector(
        R=clip(50+50*er*(1 if mom14>=0 else -1)),
        L=clip(35+45*volume_rank),
        F=50,C=50,
        P=clip(100*range_pos),
        V=clip(50+250*mom14),
        D=50,E=50,
        T=clip(100*(1-min(abs(mom14),.20)/.20)),
    )
    obs={"reclaim":max(-1,min(1,mom14*5)),"spot_cvd":0,"oi_flush":0,"supply_pressure":0,"capital_efficiency":0,"shock":0}
    out=DynamicGameEngine().analyze(DGEInput(
        symbol="BTC-USD",as_of=now.isoformat(),factors=factors,observations=obs,
        provenance={"OHLCV":ds.provenance.source_name,"F/C/D/E":"UNAVAILABLE_NEUTRAL_50"},
    )).to_dict()
    out["price"]=closes[-1]
    out["data_mode"]="PARTIAL_LIVE"
    out["live_factors"]=["R","L","P","V","T"]
    out["neutral_placeholders"]=["F","C","D","E"]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"price":out["price"],"state":out["dominant_state"],"confidence":out["confidence"],"rows":len(rows)}))
if __name__=="__main__": main()
