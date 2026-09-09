from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ...interfaces import SourceAdapter
from ...models import (
    AdjustmentPolicy, Dataset, DatasetMetadata, PlannedDataRequest, Provenance,
    SourceTier, TradingCalendarType, utc_now,
)
from ..http import JSONHTTPClient


def _epoch(date_text: str, *, inclusive_end: bool = False) -> int:
    value = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    if inclusive_end and len(date_text) == 10:
        value += timedelta(days=1)
    return int(value.timestamp())


class YahooChartAdapter(SourceAdapter):
    """No-key structured fallback. The chart endpoint is not a documented public API."""

    adapter_id = "yahoo-chart"
    priority = 30
    base_url = "https://query2.finance.yahoo.com/v8/finance/chart"

    def supports(self, request: PlannedDataRequest) -> bool:
        return (request.dataset_type == "OHLCV" and request.frequency == "1d"
                and request.asset.asset_type.upper() in {"STOCK", "EQUITY", "ETF", "CRYPTO"})

    def routing_priority(self, request: PlannedDataRequest) -> int:
        return 30 if request.asset.asset_type.upper() != "CRYPTO" else 40

    def __init__(self, http_client: JSONHTTPClient | None = None):
        self.http = http_client or JSONHTTPClient()

    def retrieve(self, request: PlannedDataRequest) -> Dataset:
        if not request.requested_start_date or not request.requested_end_date:
            raise ValueError("Yahoo retrieval requires explicit start and end dates")
        payload = self.http.get_json(
            f"{self.base_url}/{request.asset.symbol}",
            params={
                "period1": _epoch(request.requested_start_date),
                "period2": _epoch(request.requested_end_date, inclusive_end=True),
                "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true",
            },
        )
        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise RuntimeError(str(chart["error"]))
        results = chart.get("result") or []
        if not results:
            raise RuntimeError("Yahoo returned no chart result")
        return self.normalize(results[0], request)

    def normalize(self, result: dict[str, Any], request: PlannedDataRequest) -> Dataset:
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        quotes = (indicators.get("quote") or [{}])[0]
        adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
        records: list[dict[str, Any]] = []
        dropped_bars = 0
        is_crypto = request.asset.asset_type.upper() == "CRYPTO"
        for index, stamp in enumerate(timestamps):
            try:
                raw = {name: quotes.get(name, [])[index] for name in ("open", "high", "low", "close")}
            except IndexError:
                dropped_bars += 1
                continue
            if any(value is None for value in raw.values()):
                dropped_bars += 1
                continue
            factor = 1.0
            if not is_crypto and request.normalization != AdjustmentPolicy.RAW.value:
                if index >= len(adjusted) or adjusted[index] is None or not raw["close"]:
                    dropped_bars += 1
                    continue
                factor = float(adjusted[index]) / float(raw["close"])
            row = {
                "timestamp": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                "open": float(raw["open"]) * factor,
                "high": float(raw["high"]) * factor,
                "low": float(raw["low"]) * factor,
                "close": float(raw["close"]) * factor,
            }
            volumes = quotes.get("volume") or []
            if index < len(volumes) and volumes[index] is not None:
                row["volume"] = float(volumes[index])
            records.append(row)
        records.sort(key=lambda row: row["timestamp"])
        meta = result.get("meta") or {}
        adjustment = (AdjustmentPolicy.NOT_APPLICABLE.value if is_crypto
                      else AdjustmentPolicy.PROVIDER_ADJUSTED.value)
        calendar_type = (TradingCalendarType.CONTINUOUS_24_7.value if is_crypto
                         else TradingCalendarType.US_EQUITY_SESSIONS.value)
        actual_start = records[0]["timestamp"] if records else None
        actual_end = records[-1]["timestamp"] if records else None
        warnings = ["Yahoo chart is a structured but undocumented no-key fallback endpoint"]
        if dropped_bars:
            warnings.append(f"Dropped {dropped_bars} bars with incomplete OHLC/adjustment data")
        metadata = DatasetMetadata(
            request.asset.symbol, request.asset.asset_type,
            meta.get("currency") or request.asset.currency, request.frequency,
            calendar_type, adjustment, request.requested_start_date, request.requested_end_date,
            actual_start, actual_end, len(records), request.lookback_bars, warnings,
        )
        transformations = ["Yahoo chart arrays normalized to Victor OHLCV"]
        if not is_crypto and request.normalization != AdjustmentPolicy.RAW.value:
            transformations.append("OHLC multiplied by provider adjclose/close ratio; volume preserved as supplied")
        if dropped_bars:
            transformations.append(f"Removed {dropped_bars} incomplete bars during normalization")
        provenance = Provenance(
            self.adapter_id, "Yahoo Finance Chart", SourceTier.TIER_3.value,
            utc_now(), actual_end or request.requested_end_date or utc_now(),
            ("DIRECT" if is_crypto or request.normalization == AdjustmentPolicy.RAW.value
             else "RECONSTRUCTED"),
            transformations, None, adjustment,
        )
        return Dataset(request.request_key, records, provenance, False, metadata)
