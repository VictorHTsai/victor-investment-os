from __future__ import annotations

import time

from ...interfaces import DataWorker, SourceAdapter
from ...models import ComponentFailure, Dataset, FailureCode, PlannedDataRequest
from ..router import SourceRouter
from ..validation import validate_ohlcv


class MemoryTTLCache:
    def __init__(self):
        self._items: dict[str, tuple[float, Dataset]] = {}

    def get(self, key: str) -> Dataset | None:
        item = self._items.get(key)
        if not item or item[0] < time.time():
            self._items.pop(key, None)
            return None
        return item[1]

    def put(self, key: str, value: Dataset, ttl_seconds: int) -> None:
        self._items[key] = (time.time() + ttl_seconds, value)


class DataRetrievalWorker(DataWorker):
    def __init__(self, adapters: list[SourceAdapter] | None = None,
                 cache: MemoryTTLCache | None = None, router: SourceRouter | None = None):
        self.router = router or SourceRouter(adapters or [])
        self.cache = cache or MemoryTTLCache()

    def retrieve(self, request: PlannedDataRequest) -> Dataset | ComponentFailure:
        cached = self.cache.get(request.request_key)
        if cached:
            return cached
        failures = []
        for adapter in self.router.route(request):
            try:
                dataset = adapter.retrieve(request)
                validation = self._validate(request, dataset)
                if not validation.valid:
                    failures.append(f"{adapter.adapter_id}: {'; '.join(validation.errors)}")
                    continue
                if dataset.metadata:
                    dataset.metadata.warnings.extend(validation.warnings)
                    if failures:
                        dataset.metadata.warnings.append(
                            "Fallback source used after: " + "; ".join(failures)
                        )
                self.cache.put(request.request_key, dataset, request.max_age_seconds)
                return dataset
            except Exception as exc:
                failures.append(f"{adapter.adapter_id}: {exc}")
        code = FailureCode.SOURCE_FAILURE if failures else FailureCode.DATA_UNAVAILABLE
        return ComponentFailure("data_worker", code.value, "; ".join(failures) or "No adapter supports request", recoverable=True)

    @staticmethod
    def _validate(request: PlannedDataRequest, dataset: Dataset):
        if (request.dataset_type == "OHLCV"
                and {"open", "high", "low", "close"} <= request.required_fields):
            return validate_ohlcv(dataset.records, request)
        missing_errors = []
        if len(dataset.records) < request.minimum_observations:
            missing_errors.append(
                f"requires {request.minimum_observations} observations; got {len(dataset.records)}"
            )
        for index, row in enumerate(dataset.records):
            missing = request.required_fields - row.keys()
            if missing:
                missing_errors.append(f"record {index} missing fields: {sorted(missing)}")
        from ..validation import OHLCVValidationReport
        return OHLCVValidationReport(not missing_errors, missing_errors)
