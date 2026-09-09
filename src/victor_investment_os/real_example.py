from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import Asset, RequestEnvelope
from .orchestrator import build_phase2_compression_orchestrator


ASSETS = {
    "SLV": Asset("SLV", "ETF", "NYSEARCA", "USD"),
    "GLD": Asset("GLD", "ETF", "NYSEARCA", "USD"),
    "AAPL": Asset("AAPL", "STOCK", "NASDAQ", "USD"),
    "QQQ": Asset("QQQ", "ETF", "NASDAQ", "USD"),
    "BTC-USD": Asset("BTC-USD", "CRYPTO", "COINBASE", "USD"),
}


def analyze_real_asset(symbol: str, analysis_as_of: str | None = None) -> dict:
    asset = ASSETS[symbol]
    as_of = analysis_as_of or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    request = RequestEnvelope(
        "1.0", f"phase2-real-{symbol.lower()}-001", as_of, asset, "live"
    )
    return build_phase2_compression_orchestrator().analyze(request)


def main() -> None:
    print(json.dumps(analyze_real_asset("SLV"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

