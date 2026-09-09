from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ...interfaces import SourceAdapter
from ...models import (
    AdjustmentPolicy, Dataset, DatasetMetadata, PlannedDataRequest, Provenance,
    SourceTier, TradingCalendarType, utc_now,
)
from ..http import JSONHTTPClient


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class CoinbaseExchangeAdapter(SourceAdapter):
    adapter_id = "coinbase-exchange"
    priority = 5
    base_url = "https://api.exchange.coinbase.com/products"

    def __init__(self, http_client: JSONHTTPClient | None = None):
        self.http = http_client or JSONHTTPClient()

    def supports(self, request: PlannedDataRequest) -> bool:
        return (request.dataset_type == "OHLCV" and request.frequency == "1d"
                and request.asset.asset_type.upper() == "CRYPTO")

    def retrieve(self, request: PlannedDataRequest) -> Dataset:
        if not request.requested_start_date or not request.requested_end_date:
            raise ValueError("Coinbase retrieval requires explicit start and end dates")
        start = _date(request.requested_start_date)
        end = _date(request.requested_end_date)
        rows: list[list[Any]] = []
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=299), end)
            payload = self.http.get_json(
                f"{self.base_url}/{request.asset.symbol}/candles",
                params={"start": cursor.isoformat(), "end": chunk_end.isoformat(), "granularity": 86400},
            )
            if not isinstance(payload, list):
                raise RuntimeError(f"Unexpected Coinbase response: {payload}")
            rows.extend(payload)
            # Deliberately overlap the boundary; normalization de-duplicates timestamps.
            cursor = chunk_end
        return self.normalize(rows, request)

    def normalize(self, rows: list[list[Any]], request: PlannedDataRequest) -> Dataset:
        by_stamp: dict[int, dict[str, Any]] = {}
        dropped_bars = 0
        for row in rows:
            if len(row) < 6:
                dropped_bars += 1
                continue
            stamp, low, high, open_, close, volume = row[:6]
            by_stamp[int(stamp)] = {
                "timestamp": datetime.fromtimestamp(int(stamp), timezone.utc).isoformat(),
                "open": float(open_), "high": float(high), "low": float(low),
                "close": float(close), "volume": float(volume),
            }
        records = [by_stamp[key] for key in sorted(by_stamp)]
        actual_start = records[0]["timestamp"] if records else None
        actual_end = records[-1]["timestamp"] if records else None
        adjustment = AdjustmentPolicy.NOT_APPLICABLE.value
        warnings = ([f"Dropped {dropped_bars} malformed Coinbase candles"] if dropped_bars else [])
        metadata = DatasetMetadata(
            request.asset.symbol, request.asset.asset_type, request.asset.currency, request.frequency,
            TradingCalendarType.CONTINUOUS_24_7.value, adjustment,
            request.requested_start_date, request.requested_end_date, actual_start, actual_end,
            len(records), request.lookback_bars, warnings,
        )
        provenance = Provenance(
            self.adapter_id, "Coinbase Exchange", SourceTier.TIER_1.value,
            utc_now(), actual_end or request.requested_end_date or utc_now(), "DIRECT",
            ["Coinbase candle arrays normalized to Victor OHLCV", "Paged in <=300-day requests"]
            + ([f"Removed {dropped_bars} malformed candles during normalization"] if dropped_bars else []),
            None, adjustment,
        )
        return Dataset(request.request_key, records, provenance, False, metadata)
