from copy import deepcopy

from victor_investment_os.data.validation import validate_ohlcv
from test_real_adapters_and_routing import planned


VALID = [
    {"timestamp": "2024-01-02T00:00:00Z", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100},
    {"timestamp": "2024-01-03T00:00:00Z", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 110},
]


def test_valid_ohlcv_passes():
    report = validate_ohlcv(VALID, planned())
    assert report.valid


def test_duplicate_unordered_and_invalid_ohlc_are_rejected():
    rows = deepcopy(VALID)
    rows[1]["timestamp"] = rows[0]["timestamp"]
    rows[1]["high"] = 8
    report = validate_ohlcv(rows, planned())
    assert not report.valid
    assert any("duplicate" in error for error in report.errors)
    assert any("high below" in error for error in report.errors)


def test_missing_optional_volume_is_warning_not_failure():
    rows = [{key: value for key, value in row.items() if key != "volume"} for row in VALID]
    report = validate_ohlcv(rows, planned())
    assert report.valid
    assert report.volume_available is False
    assert report.warnings

