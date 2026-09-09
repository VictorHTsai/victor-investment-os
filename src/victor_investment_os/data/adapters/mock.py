from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ...interfaces import SourceAdapter
from ...models import Dataset, PlannedDataRequest, Provenance, utc_now


class MockMarketDataAdapter(SourceAdapter):
    adapter_id = "mock-market-data"
    priority = 1

    def __init__(self, fail: bool = False):
        self.fail = fail

    def supports(self, request: PlannedDataRequest) -> bool:
        return request.dataset_type == "OHLCV"

    def retrieve(self, request: PlannedDataRequest) -> Dataset:
        if self.fail:
            raise ConnectionError("Intentional mock source failure")
        count = max(request.minimum_observations, request.lookback_days)
        end = datetime.fromisoformat("2026-09-09T00:00:00+00:00")
        records = []
        for i in range(count):
            close = round(20 + i * 0.01 + ((i % 20) - 10) * 0.02, 4)
            row = {"timestamp": (end - timedelta(days=count - i - 1)).isoformat()}
            values = {"open": close - 0.05, "high": close + 0.2, "low": close - 0.2, "close": close, "volume": 1_000_000 + i * 100}
            row.update({k: values[k] for k in request.required_fields if k in values})
            records.append(row)
        return Dataset(request.request_key, records, Provenance(
            source_id=self.adapter_id, source_name="Mock Market Data Adapter",
            source_tier="MOCK", retrieved_at=utc_now(), source_timestamp=end.isoformat(),
            data_type="DIRECT", transformations=["synthetic deterministic fixture"], confidence=1.0,
        ), is_mock=True)

