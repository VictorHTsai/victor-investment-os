from __future__ import annotations

import os
from typing import Any

from ...interfaces import SourceAdapter
from ...models import (
    AdjustmentPolicy, Dataset, DatasetMetadata, PlannedDataRequest, Provenance,
    SourceTier, TradingCalendarType, utc_now,
)
from ..http import JSONHTTPClient


class AlpacaMarketDataAdapter(SourceAdapter):
    adapter_id = "alpaca-market-data"
    priority = 10
    base_url = "https://data.alpaca.markets/v2/stocks"

    def __init__(self, http_client: JSONHTTPClient | None = None,
                 api_key: str | None = None, api_secret: str | None = None,
                 use_environment: bool = True):
        self.http = http_client or JSONHTTPClient()
        self.api_key = api_key if api_key is not None else (
            os.getenv("ALPACA_API_KEY_ID") if use_environment else None
        )
        self.api_secret = api_secret if api_secret is not None else (
            os.getenv("ALPACA_API_SECRET_KEY") if use_environment else None
        )

    def supports(self, request: PlannedDataRequest) -> bool:
        return (request.dataset_type == "OHLCV" and request.frequency == "1d"
                and request.asset.asset_type.upper() in {"STOCK", "EQUITY", "ETF"})

    def retrieve(self, request: PlannedDataRequest) -> Dataset:
        if not self.api_key or not self.api_secret:
            raise RuntimeError("ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY are not configured")
        if not request.requested_start_date or not request.requested_end_date:
            raise ValueError("Alpaca retrieval requires explicit start and end dates")
        headers = {"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.api_secret}
        params: dict[str, Any] = {
            "timeframe": "1Day", "start": request.requested_start_date,
            "end": request.requested_end_date, "adjustment": "all", "feed": "iex",
            "limit": 10_000, "sort": "asc",
        }
        bars: list[dict[str, Any]] = []
        while True:
            payload = self.http.get_json(
                f"{self.base_url}/{request.asset.symbol}/bars", params=params, headers=headers
            )
            bars.extend(payload.get("bars") or [])
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        return self.normalize(bars, request)

    def normalize(self, bars: list[dict[str, Any]], request: PlannedDataRequest) -> Dataset:
        records = [{
            "timestamp": bar["t"], "open": float(bar["o"]), "high": float(bar["h"]),
            "low": float(bar["l"]), "close": float(bar["c"]), "volume": float(bar["v"]),
        } for bar in bars]
        records.sort(key=lambda row: row["timestamp"])
        actual_start = records[0]["timestamp"] if records else None
        actual_end = records[-1]["timestamp"] if records else None
        adjustment = AdjustmentPolicy.SPLIT_DIVIDEND_ADJUSTED.value
        metadata = DatasetMetadata(
            request.asset.symbol, request.asset.asset_type, request.asset.currency, request.frequency,
            TradingCalendarType.US_EQUITY_SESSIONS.value, adjustment,
            request.requested_start_date, request.requested_end_date, actual_start, actual_end,
            len(records), request.lookback_bars,
            ["Alpaca Basic uses the IEX feed; volume is not consolidated-market volume"],
        )
        provenance = Provenance(
            self.adapter_id, "Alpaca Market Data API", SourceTier.TIER_2.value,
            utc_now(), actual_end or request.requested_end_date or utc_now(), "DIRECT",
            ["Alpaca adjustment=all", "Alpaca IEX daily bars normalized to Victor OHLCV"],
            None, adjustment,
        )
        return Dataset(request.request_key, records, provenance, False, metadata)
