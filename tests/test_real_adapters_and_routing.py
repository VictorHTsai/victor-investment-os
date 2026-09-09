from datetime import datetime, timezone

from victor_investment_os.data.adapters import (
    AlpacaMarketDataAdapter, CoinbaseExchangeAdapter, YahooChartAdapter,
)
from victor_investment_os.data.router import SourceRouter
from victor_investment_os.data.worker import DataRetrievalWorker
from victor_investment_os.models import Asset, Dataset, PlannedDataRequest


class FakeHTTP:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.payload


def planned(asset_type="ETF", symbol="SLV", normalization="SPLIT_DIVIDEND_ADJUSTED"):
    return PlannedDataRequest(
        "key", Asset(symbol, asset_type, "TEST", "USD"), "OHLCV", "1d", 100, 2,
        frozenset({"timestamp", "open", "high", "low", "close"}), 60,
        "DISALLOW", normalization, ("compression",), lookback_bars=60,
        requested_start_date="2020-01-01", requested_end_date="2026-01-01",
        optional_fields=frozenset({"volume"}), historical_context_years=5,
        trading_calendar_type=("CONTINUOUS_24_7" if asset_type == "CRYPTO" else "US_EQUITY_SESSIONS"),
    )


def yahoo_payload():
    stamps = [int(datetime(2024, 1, day, tzinfo=timezone.utc).timestamp()) for day in (2, 3)]
    return {"chart": {"error": None, "result": [{
        "timestamp": stamps,
        "meta": {"currency": "USD"},
        "indicators": {
            "quote": [{"open": [99, 109], "high": [102, 112], "low": [98, 108],
                       "close": [100, 110], "volume": [1000, 1100]}],
            "adjclose": [{"adjclose": [50, 55]}],
        },
    }]}}


def test_yahoo_real_adapter_normalization_and_adjustment_metadata():
    adapter = YahooChartAdapter(FakeHTTP(yahoo_payload()))
    dataset = adapter.retrieve(planned())
    assert dataset.records[0]["close"] == 50
    assert dataset.records[0]["open"] == 49.5
    assert dataset.records[0]["volume"] == 1000
    assert dataset.metadata.adjustment_policy == "PROVIDER_ADJUSTED"
    assert dataset.metadata.currency == "USD"
    assert dataset.provenance.source_tier == "TIER_3"
    assert dataset.provenance.data_type == "RECONSTRUCTED"
    assert "adjclose/close" in " ".join(dataset.provenance.transformations)


def test_alpaca_normalization_records_corporate_action_policy():
    bars = [{"t": "2024-01-02T05:00:00Z", "o": 10, "h": 12, "l": 9, "c": 11, "v": 100},
            {"t": "2024-01-03T05:00:00Z", "o": 11, "h": 13, "l": 10, "c": 12, "v": 120}]
    dataset = AlpacaMarketDataAdapter(api_key="x", api_secret="y").normalize(bars, planned())
    assert dataset.metadata.adjustment_policy == "SPLIT_DIVIDEND_ADJUSTED"
    assert dataset.provenance.source_tier == "TIER_2"
    assert dataset.records[1]["close"] == 12


def test_coinbase_normalizes_and_sorts_exchange_candles():
    rows = [[1704240000, 40, 50, 42, 48, 10], [1704153600, 35, 45, 38, 42, 9]]
    dataset = CoinbaseExchangeAdapter().normalize(rows, planned("CRYPTO", "BTC-USD", "NOT_APPLICABLE"))
    assert dataset.records[0]["close"] == 42
    assert dataset.metadata.trading_calendar_type == "CONTINUOUS_24_7"
    assert dataset.metadata.adjustment_policy == "NOT_APPLICABLE"
    assert dataset.provenance.source_tier == "TIER_1"


def test_source_routing_is_asset_and_dataset_aware():
    router = SourceRouter([
        YahooChartAdapter(FakeHTTP(yahoo_payload())), AlpacaMarketDataAdapter(), CoinbaseExchangeAdapter()
    ])
    equity_routes = [item.adapter_id for item in router.route(planned())]
    crypto_routes = [item.adapter_id for item in router.route(planned("CRYPTO", "BTC-USD", "NOT_APPLICABLE"))]
    assert equity_routes == ["alpaca-market-data", "yahoo-chart"]
    assert crypto_routes == ["coinbase-exchange", "yahoo-chart"]


def test_worker_falls_back_when_primary_credentials_are_absent():
    request = planned()
    worker = DataRetrievalWorker(router=SourceRouter([
        AlpacaMarketDataAdapter(use_environment=False),
        YahooChartAdapter(FakeHTTP(yahoo_payload())),
    ]))
    result = worker.retrieve(request)
    assert isinstance(result, Dataset)
    assert result.provenance.source_id == "yahoo-chart"
    assert any("Fallback source used" in warning for warning in result.metadata.warnings)
