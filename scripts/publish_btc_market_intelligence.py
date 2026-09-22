from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
OUT=Path("apps/dge-dashboard/data/market-intelligence.json")
def get_json(url):
    with urlopen(Request(url,headers={"User-Agent":"Victor-Investment-OS"}),timeout=20) as r:
        return json.loads(r.read().decode())
def pct(a,b): return (a/b-1)*100 if b else 0
def main():
    out={"schema_version":"btc-market-intelligence-v1","as_of":datetime.now(timezone.utc).isoformat(),"modules":{},"history":{}}
    try:
        funding=get_json("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=90")
        oi=get_json("https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1d&limit=30")
        fr=[float(x["fundingRate"])*100 for x in funding]; ov=[float(x["sumOpenInterestValue"]) for x in oi]
        oi7=pct(ov[-1],ov[-8]) if len(ov)>=8 else 0; favg=sum(fr[-21:])/min(21,len(fr))
        status="DELEVERAGING" if oi7<=-5 else "CROWDED" if oi7>=10 and favg>0.02 else "NEUTRAL" if abs(oi7)<5 and abs(favg)<0.02 else "ACTIVE"
        out["modules"]["derivatives"]={"status":status,"funding_avg_pct":round(favg,4),"open_interest_7d_change_pct":round(oi7,2),"source":"Binance public futures API"}
        out["history"]["open_interest"]=[{"date":datetime.fromtimestamp(int(x["timestamp"])/1000,timezone.utc).date().isoformat(),"value":float(x["sumOpenInterestValue"])} for x in oi]
    except Exception as e: out["modules"]["derivatives"]={"status":"DATA PENDING","error":str(e)[:100]}
    try:
        candles=sorted(get_json("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400"),key=lambda x:x[0])[-90:]
        closes=[float(x[4]) for x in candles]; vols=[float(x[5]) for x in candles]
        rets=[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]
        rv7=(sum(x*x for x in rets[-7:])/7)**.5*math.sqrt(365)*100; rv30=(sum(x*x for x in rets[-30:])/30)**.5*math.sqrt(365)*100
        vr=(sum(vols[-7:])/7)/(sum(vols[-30:])/30); dd=(closes[-1]/max(closes[-30:])-1)*100
        score=int(rv7>rv30*1.25)+int(vr>1.3)+int(dd<-10); status=["LOW","NORMAL","ELEVATED","EXTREME"][score]
        out["modules"]["stress"]={"status":status,"realized_vol_7d_pct":round(rv7,1),"realized_vol_30d_pct":round(rv30,1),"volume_ratio":round(vr,2),"drawdown_30d_pct":round(dd,1),"source":"Coinbase Exchange public candles"}
    except Exception as e: out["modules"]["stress"]={"status":"DATA PENDING","error":str(e)[:100]}
    out["modules"]["capital_flow"]={"status":"DATA PENDING","note":"ETF flow source validation pending"}
    out["modules"]["liquidity"]={"status":"DATA PENDING","note":"Stablecoin time-series source validation pending"}
    out["modules"]["supply"]={"status":"DATA PENDING","note":"Reliable on-chain cohort source not yet integrated"}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2)+"\n")
if __name__=="__main__": main()
