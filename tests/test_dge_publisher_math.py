from victor_investment_os.engines.dynamic_game.features import percentile_rank

def test_percentile_rank_high_value():
    assert percentile_rank(4,[1,2,3,4]) == 1

def test_percentile_rank_mid_value():
    assert percentile_rank(2,[1,2,3,4]) == .5
