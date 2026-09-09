from __future__ import annotations

import time

from ...interfaces import DataWorker, SourceAdapter
from ...models import ComponentFailure, Dataset, FailureCode, PlannedDataRequest


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
    def __init__(self, adapters: list[SourceAdapter], cache: MemoryTTLCache | None = None):
        self.adapters = sorted(adapters, key=lambda a: a.priority)
        self.cache = cache or MemoryTTLCache()

    def retrieve(self, request: PlannedDataRequest) -> Dataset | ComponentFailure:
        cached = self.cache.get(request.request_key)
        if cached:
            return cached
        failures = []
        for adapter in self.adapters:
            if not adapter.supports(request):
                continue
            try:
                dataset = adapter.retrieve(request)
                validation = self._validate(request, dataset)
                if validation:
                    failures.append(f"{adapter.adapter_id}: {validation}")
                    continue
                self.cache.put(request.request_key, dataset, request.max_age_seconds)
                return dataset
            except Exception as exc:
                failures.append(f"{adapter.adapter_id}: {exc}")
        code = FailureCode.SOURCE_FAILURE if failures else FailureCode.DATA_UNAVAILABLE
        return ComponentFailure("data_worker", code.value, "; ".join(failures) or "No adapter supports request", recoverable=True)

    @staticmethod
    def _validate(request: PlannedDataRequest, dataset: Dataset) -> str | None:
        if len(dataset.records) < request.minimum_observations:
            return f"requires {request.minimum_observations} observations; got {len(dataset.records)}"
        for index, row in enumerate(dataset.records):
            missing = request.required_fields - row.keys()
            if missing:
                return f"record {index} missing fields: {sorted(missing)}"
        return None
