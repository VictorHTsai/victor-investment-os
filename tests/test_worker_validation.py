from victor_investment_os.data.adapters import MockMarketDataAdapter
from victor_investment_os.data.worker import DataRetrievalWorker
from victor_investment_os.interfaces import SourceAdapter
from victor_investment_os.models import Asset, Dataset, PlannedDataRequest, Provenance


REQ = PlannedDataRequest("key", Asset("SLV", "ETF", "NYSEARCA", "USD"), "OHLCV", "1d", 10, 2,
                         frozenset({"close"}), 60, "DISALLOW", "RAW", ("technical",))


class InvalidAdapter(SourceAdapter):
    adapter_id = "invalid"
    priority = 0
    def supports(self, request): return True
    def retrieve(self, request):
        provenance = Provenance("invalid", "Invalid", "MOCK", "2026-09-09T00:00:00Z",
                                "2026-09-09T00:00:00Z", "DIRECT")
        return Dataset(request.request_key, [{"wrong": 1}, {"wrong": 2}], provenance, True)


def test_worker_falls_back_after_validation_failure():
    result = DataRetrievalWorker([InvalidAdapter(), MockMarketDataAdapter()]).retrieve(REQ)
    assert isinstance(result, Dataset)
    assert result.provenance.source_id == "mock-market-data"

