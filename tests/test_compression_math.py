from math import isclose, log, sqrt
from statistics import pstdev

from victor_investment_os.engines.compression import CompressionEngineV1, percentile_rank


def test_percentile_convention_is_inclusive_and_reproducible():
    assert percentile_rank([1, 2, 3], 1) == 0
    assert percentile_rank([1, 2, 3], 2) == 0.5
    assert percentile_rank([1, 2, 3], 3) == 1
    assert percentile_rank([1, 2, 2, 3], 2) == 0.5


def test_realized_volatility_uses_log_returns():
    closes = [100, 101, 99, 102]
    returns = [None] + [log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    result = CompressionEngineV1._rolling_realized_volatility(returns, 3, 252)
    expected = pstdev(returns[1:]) * sqrt(252)
    assert isclose(result[-1], expected)


def test_normalized_atr_formula():
    tr = [2, 4, 3]
    closes = [10, 11, 12]
    result = CompressionEngineV1._rolling_normalized_atr(tr, closes, 3)
    assert isclose(result[-1], 3 / 12)


def test_bollinger_band_width_formula():
    closes = [10, 12, 14]
    result = CompressionEngineV1._rolling_bbw(closes, 3, 2)
    assert isclose(result[-1], 4 * pstdev(closes) / 12)


def test_rolling_price_range_formula():
    result = CompressionEngineV1._rolling_range([11, 13, 15], [9, 10, 12], [10, 12, 14], 3)
    assert isclose(result[-1], (15 - 9) / 14)


def test_volume_activity_formula():
    volumes = [float(i) for i in range(1, 7)]
    result = CompressionEngineV1._rolling_volume_activity(volumes, 2, 4)
    assert isclose(result[-1], ((5 + 6) / 2) / ((3 + 4 + 5 + 6) / 4))

