import importlib.util
from pathlib import Path

from victor_investment_os.data.validation import validate_ohlcv

from test_real_adapters_and_routing import FakeHTTP, planned


SCRIPT = Path(__file__).parents[1] / "scripts" / "benchmark_data_sources.py"
SPEC = importlib.util.spec_from_file_location("benchmark_data_sources", SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(benchmark)
data_summaries = benchmark.data_summaries
pairwise_differences = benchmark.pairwise_differences
retrieve_tiingo = benchmark.retrieve_tiingo


def test_tiingo_benchmark_path_uses_adjusted_ohlcv_and_volume():
    payload = [{
        "date": "2024-01-02T00:00:00.000Z",
        "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000,
        "adjOpen": 50, "adjHigh": 55, "adjLow": 45, "adjClose": 52.5,
        "adjVolume": 2000, "divCash": 0, "splitFactor": 2,
    }, {
        "date": "2024-01-03T00:00:00.000Z",
        "open": 106, "high": 112, "low": 101, "close": 110, "volume": 1200,
        "adjOpen": 53, "adjHigh": 56, "adjLow": 50.5, "adjClose": 55,
        "adjVolume": 2400, "divCash": 0, "splitFactor": 1,
    }]
    request = planned()
    dataset = retrieve_tiingo(request, "test-token", FakeHTTP(payload))

    assert dataset.records[0]["open"] == 50
    assert dataset.records[0]["volume"] == 2000
    assert dataset.provenance.adjustment_policy == "SPLIT_DIVIDEND_ADJUSTED"
    assert validate_ohlcv(dataset.records, request).valid


def test_date_alignment_and_descriptive_difference_metrics():
    payload_a = [{
        "date": "2024-01-02T00:00:00Z", "adjOpen": 10, "adjHigh": 12,
        "adjLow": 9, "adjClose": 11, "adjVolume": 100,
    }, {
        "date": "2024-01-03T00:00:00Z", "adjOpen": 11, "adjHigh": 13,
        "adjLow": 10, "adjClose": 12, "adjVolume": 120,
    }]
    payload_b = [{**payload_a[0], "adjClose": 10}, {
        "date": "2024-01-04T00:00:00Z", "adjOpen": 12, "adjHigh": 14,
        "adjLow": 11, "adjClose": 13, "adjVolume": 130,
    }]
    request = planned()
    datasets = {
        "a": retrieve_tiingo(request, "token", FakeHTTP(payload_a)),
        "b": retrieve_tiingo(request, "token", FakeHTTP(payload_b)),
    }
    start = datasets["a"].metadata.actual_start_date[:10]
    end = datasets["b"].metadata.actual_end_date[:10]
    from datetime import date
    summaries = data_summaries(datasets, date.fromisoformat(start), date.fromisoformat(end))
    differences = pairwise_differences(datasets, date.fromisoformat(start), date.fromisoformat(end))

    assert summaries[0]["source_only_dates"] == 1
    assert summaries[0]["dates_missing_relative_to_other_sources"] == 1
    assert differences[0]["overlapping_dates"] == 1
    assert differences[0]["fields"]["close"]["mean_absolute_difference"] == 1
