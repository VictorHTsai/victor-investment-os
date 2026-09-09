from datetime import datetime, timedelta, timezone
from math import sin
import json
from pathlib import Path

import jsonschema

from victor_investment_os.engines.compression import CompressionEngineV1
from victor_investment_os.models import (
    Asset, Dataset, DatasetMetadata, Provenance, RequestEnvelope,
)


END = datetime(2026, 9, 9, tzinfo=timezone.utc)


def make_dataset(years=6, crypto=False, volume=True):
    start = END - timedelta(days=round(years * 365.25))
    rows = []
    cursor = start
    i = 0
    while cursor <= END:
        if crypto or cursor.weekday() < 5:
            close = 100 + 0.015 * i + 3 * sin(i / 19) + 1.5 * sin(i / 7)
            open_ = close * (1 + 0.001 * sin(i / 5))
            row = {
                "timestamp": cursor.isoformat(), "open": open_,
                "high": max(open_, close) + 1.0, "low": min(open_, close) - 1.0,
                "close": close,
            }
            if volume:
                row["volume"] = 1_000_000 + 10_000 * sin(i / 13) + i
            rows.append(row)
            i += 1
        cursor += timedelta(days=1)
    calendar = "CONTINUOUS_24_7" if crypto else "US_EQUITY_SESSIONS"
    adjustment = "NOT_APPLICABLE" if crypto else "SPLIT_DIVIDEND_ADJUSTED"
    metadata = DatasetMetadata(
        "BTC-USD" if crypto else "SLV", "CRYPTO" if crypto else "ETF", "USD", "1d",
        calendar, adjustment, start.date().isoformat(), END.date().isoformat(),
        rows[0]["timestamp"], rows[-1]["timestamp"], len(rows), 252, [],
    )
    provenance = Provenance(
        "fixture", "Deterministic Fixture", "TIER_2", "2026-09-09T00:00:00Z",
        rows[-1]["timestamp"], "DIRECT", ["test fixture"], None, adjustment,
    )
    return Dataset("fixture", rows, provenance, False, metadata)


def request(crypto=False):
    asset = Asset("BTC-USD", "CRYPTO", "COINBASE", "USD") if crypto else Asset("SLV", "ETF", "NYSEARCA", "USD")
    return RequestEnvelope("1.0", "compression-test", END.isoformat(), asset)


def output(dataset, crypto=False):
    return CompressionEngineV1().analyze(request(crypto), dataset)


def test_lookback_bars_and_calendar_context_semantics_are_separate():
    requirement = CompressionEngineV1().requirements(request())[0]
    assert requirement.lookback_bars == 252
    assert requirement.historical_context_years == 5
    assert requirement.requested_start_date == "2019-09-08"
    assert requirement.requested_end_date == "2026-09-08"


def test_3y_and_5y_percentile_contexts_use_date_boundaries():
    result = output(make_dataset())
    feature = result["features"]["bollinger_band_width"][0]
    five = feature["historical_contexts"]["5y"]
    three = feature["historical_contexts"]["3y"]
    assert five["context_start_date"] == "2021-09-09"
    assert three["context_start_date"] == "2023-09-09"
    assert five["observation_count"] > three["observation_count"]
    assert five["status"] == three["status"] == "AVAILABLE"


def test_compression_percentile_is_explicit_inversion():
    result = output(make_dataset())
    context = result["features"]["normalized_atr"][0]["historical_contexts"]["5y"]
    assert abs(context["raw_percentile"] + context["compression_percentile"] - 1) < 1e-12
    assert context["compression_inversion_applied"] is True


def test_volume_is_contextual_and_not_inverted():
    result = output(make_dataset())
    context = result["features"]["volume_activity"][0]["historical_contexts"]["5y"]
    assert context["raw_percentile"] is not None
    assert context["compression_percentile"] is None
    assert context["compression_inversion_applied"] is False


def test_missing_volume_does_not_fail_other_features():
    result = output(make_dataset(volume=False))
    assert result["status"] == "PARTIAL"
    assert result["features"]["volume_activity"][0]["status"] == "UNAVAILABLE"
    assert result["features"]["realized_volatility"][0]["status"] == "AVAILABLE"


def test_insufficient_5y_history_still_returns_valid_3y_context():
    result = output(make_dataset(years=4))
    feature = result["features"]["rolling_price_range"][0]
    assert feature["historical_contexts"]["5y"]["status"] == "INSUFFICIENT_DATA"
    assert feature["historical_contexts"]["3y"]["status"] == "AVAILABLE"


def test_five_and_twenty_bar_changes_are_exact_differences():
    result = output(make_dataset())
    context = result["features"]["realized_volatility"][0]["historical_contexts"]["5y"]
    assert context["compression_percentile_5_bars_ago"] is not None
    assert context["compression_percentile_20_bars_ago"] is not None
    assert abs(context["compression_percentile_change_5_bars"] - (
        context["compression_percentile"] - context["compression_percentile_5_bars_ago"])) < 1e-12


def test_provenance_is_propagated_and_output_is_deterministic():
    dataset = make_dataset(crypto=True)
    first = output(dataset, crypto=True)
    second = output(dataset, crypto=True)
    assert first == second
    assert first["provenance"][0]["source_id"] == "fixture"
    assert first["data_quality"]["trading_calendar_type"] == "CONTINUOUS_24_7"
    assert first["configuration"]["realized_volatility_annualization_factor"] == 365


def test_real_feature_vector_validates_against_contract():
    schema_path = Path(__file__).parents[1] / "contracts" / "v1" / "compression_engine.schema.json"
    jsonschema.validate(output(make_dataset()), json.loads(schema_path.read_text()))
