from victor_investment_os.models import Asset, DataRequirement
from victor_investment_os.planner import DataRequestPlanner


ASSET = Asset("SLV", "ETF", "NYSEARCA", "USD")


def requirement(requester, lookback, minimum, fields, **overrides):
    values = dict(requester=requester, asset=ASSET, dataset_type="OHLCV", frequency="1d",
                  lookback_days=lookback, minimum_observations=minimum,
                  required_fields=frozenset(fields), max_age_seconds=86_400,
                  proxy_policy="ALLOW", normalization="SPLIT_ADJUSTED")
    values.update(overrides)
    return DataRequirement(**values)


def test_merges_union_and_strictest_requirements():
    items = [requirement("compression", 756, 500, {"high", "low", "close", "volume"}, max_age_seconds=3600),
             requirement("technical", 1260, 750, {"open", "high", "low", "close", "volume"},
                         proxy_policy="DISALLOW")]
    result = DataRequestPlanner().plan(items)
    assert len(result) == 1
    assert result[0].lookback_days == 1260
    assert result[0].minimum_observations == 750
    assert result[0].required_fields == {"open", "high", "low", "close", "volume"}
    assert result[0].max_age_seconds == 3600
    assert result[0].proxy_policy == "DISALLOW"
    assert result[0].consumers == ("compression", "technical")


def test_deduplicates_identical_requests():
    item = requirement("technical", 100, 50, {"close"})
    result = DataRequestPlanner().plan([item, item])
    assert len(result) == 1
    assert result[0].consumers == ("technical",)


def test_incompatible_frequency_or_normalization_do_not_merge():
    items = [requirement("one", 100, 50, {"close"}),
             requirement("two", 100, 50, {"close"}, frequency="1h"),
             requirement("three", 100, 50, {"close"}, normalization="RAW")]
    assert len(DataRequestPlanner().plan(items)) == 3

