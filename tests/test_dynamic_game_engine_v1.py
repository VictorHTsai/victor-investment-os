import math
import pytest
from victor_investment_os.engines.dynamic_game import DynamicGameEngine, DGEInput, FactorVector
from victor_investment_os.engines.dynamic_game.features import (
    kaufman_efficiency, external_capital_score, control_proxy,
    test_response, capital_efficiency, cycle_prior,
)

def inp(factors, **obs):
    return DGEInput(symbol="BTC-USD", as_of="2026-09-22T00:00:00Z", factors=FactorVector(**factors), observations=obs)

def test_factor_vector_clips_to_0_100():
    f=FactorVector(R=-1,L=101,F=50,C=50,P=50,V=50,D=50,E=50,T=50)
    assert f.R == 0 and f.L == 100

def test_kaufman_efficiency_trend_is_one():
    assert kaufman_efficiency([1,2,3,4,5],4) == pytest.approx(1)

def test_external_capital_score_neutral():
    assert external_capital_score({"spot":0,"etf":0}) == pytest.approx(50)

def test_control_proxy():
    assert control_proxy(20,100) == pytest.approx(20)

def test_control_proxy_rejects_zero_float():
    with pytest.raises(ValueError): control_proxy(1,0)

def test_test_response_uses_absolute_price_shock():
    assert test_response(10,-2) == pytest.approx(5)

def test_capital_efficiency():
    assert capital_efficiency(2,4) == pytest.approx(.5)

def test_cycle_prior_half_life():
    assert cycle_prior(336) == pytest.approx(50, rel=1e-6)

def test_state_probabilities_sum_to_one():
    f={k:50 for k in "RLFC PVDET".replace(" ","")}
    out=DynamicGameEngine().analyze(inp(f))
    assert sum(out.states.as_dict().values()) == pytest.approx(1)

def test_markup_pattern_scores_markup():
    f=dict(R=70,L=75,F=90,C=55,P=65,V=65,D=30,E=20,T=55)
    out=DynamicGameEngine().analyze(inp(f, reclaim=.9, spot_cvd=.9, oi_flush=.3, supply_pressure=-.5, capital_efficiency=.8))
    assert out.dominant_state == "markup"

def test_distribution_pattern_scores_distribution():
    f=dict(R=60,L=65,F=75,C=65,P=40,V=30,D=90,E=20,T=45)
    out=DynamicGameEngine().analyze(inp(f, spot_cvd=-.6, supply_pressure=.9, capital_efficiency=-.7))
    assert out.dominant_state == "distribution"

def test_event_shock_reduces_confidence():
    base=dict(R=70,L=75,F=90,C=55,P=65,V=65,D=30,E=10,T=55)
    calm=DynamicGameEngine().analyze(inp(base,reclaim=.9,spot_cvd=.9))
    shocked=DynamicGameEngine().analyze(inp({**base,"E":95},reclaim=.9,spot_cvd=.9,shock=1))
    assert shocked.confidence < calm.confidence
