from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
OUT=Path("apps/dge-dashboard/data/market-intelligence.json")
def get_json(url):
    with urlopen(Request(url,headers={"User-Agent":"Victor-Investment-OS"}),timeout=20) as r:return json.loads(r.read().decode())
def pct(a,b): return (a/b-1)*100 if b else 0
def percentile(xs,x):
    return round(100*sum(v<=x for v in xs)/len(xs),1) if xs else None
def bybit_derivatives():
    fr=get_json("https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=90")["result"]["list"]
    oi=get_json("https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=1d&limit=30")["result"]["list"]
    fr=sorted(fr,key=lambda x:int(x["fundingRateTimestamp"])); oi=sorted(oi,key=lambda x:int(x["timestamp"]))
    rates=[float(x["fundingRate"])*100 for x in fr]; ovs=[float(x["openInterest"]) for x in oi]
    return rates,ovs,"Bybit Public API"
def binance_derivatives():
    fr=get_json("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=90")
    oi=get_json("https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1d&limit=30")
    rates=[float(x["fundingRate"])*100 for x in fr]; ovs=[float(x["sumOpenInterest"]) for x in oi]
    return rates,ovs,"Binance Public API"
def main():
    out={"schema_version":"btc-market-intelligence-v2","as_of":datetime.now(timezone.utc).isoformat(),"modules":{},"history":{}}
    errors=[]
    for provider in (bybit_derivatives,binance_derivatives):
        try:
            rates,ovs,source=provider(); oi7=pct(ovs[-1],ovs[-8]); f7=sum(rates[-21:])/min(21,len(rates)); f30=sum(rates)/len(rates)
            fp=percentile(rates,rates[-1]); op=percentile(ovs,ovs[-1])
            status="DELEVERAGING" if oi7<=-5 else "CROWDED" if oi7>=10 and f7>0.02 else "NEUTRAL" if abs(oi7)<5 and abs(f7)<0.02 else "ACTIVE"
            print("DERIVATIVES_PROVIDER_OK", source, "funding_records=", len(rates), "oi_records=", len(ovs), flush=True)
            out["modules"]["derivatives"]={"status":status,"funding_7d_avg_pct":round(f7,4),"funding_30d_avg_pct":round(f30,4),"funding_30d_percentile":fp,"open_interest_7d_change_pct":round(oi7,2),"open_interest_30d_percentile":op,"source":source}
            break
        except Exception as e:
            msg=provider.__name__+": "+type(e).__name__+": "+str(e)[:300]
            errors.append(msg)
            print("DERIVATIVES_PROVIDER_FAIL", msg, flush=True)
    else:
        print("DERIVATIVES_ALL_PROVIDERS_FAILED", " | ".join(errors), flush=True)
        out["modules"]["derivatives"]={"status":"DATA PENDING","error":" | ".join(errors),"providers_attempted":["Bybit Public API","Binance Public API"]}
    try:
        candles=sorted(get_json("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400"),key=lambda x:x[0])[-90:]
        closes=[float(x[4]) for x in candles]; vols=[float(x[5]) for x in candles]; rets=[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]
        rv7=(sum(x*x for x in rets[-7:])/7)**.5*math.sqrt(365)*100; rv30=(sum(x*x for x in rets[-30:])/30)**.5*math.sqrt(365)*100
        vr=(sum(vols[-7:])/7)/(sum(vols[-30:])/30); dd=(closes[-1]/max(closes[-30:])-1)*100; p7=pct(closes[-1],closes[-8])
        score=int(rv7>rv30*1.25)+int(vr>1.3)+int(dd<-10); status=["LOW","NORMAL","ELEVATED","EXTREME"][score]
        out["modules"]["stress"]={"status":status,"btc_price_7d_change_pct":round(p7,2),"realized_vol_7d_pct":round(rv7,1),"realized_vol_30d_pct":round(rv30,1),"volume_ratio":round(vr,2),"drawdown_30d_pct":round(dd,1),"source":"Coinbase Exchange public candles"}
    except Exception as e: out["modules"]["stress"]={"status":"DATA PENDING","error":str(e)[:100]}
    out["modules"]["capital_flow"]={"status":"DATA PENDING","note":"ETF flow source validation pending"}
    out["modules"]["liquidity"]={"status":"DATA PENDING","note":"Stablecoin time-series source validation pending"}
    out["modules"]["supply"]={"status":"DATA PENDING","note":"Reliable on-chain cohort source not yet integrated"}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2)+"
")
if __name__=="__main__":main()
