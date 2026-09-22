from __future__ import annotations
from math import exp, sqrt
from statistics import mean, pstdev
from typing import Sequence

EPS = 1e-12

def zscore(value: float, history: Sequence[float]) -> float:
    xs = [float(x) for x in history]
    if len(xs) < 2:
        return 0.0
    sd = pstdev(xs)
    return 0.0 if sd <= EPS else (float(value) - mean(xs)) / sd

def kaufman_efficiency(prices: Sequence[float], lookback: int = 14) -> float:
    xs = [float(x) for x in prices]
    if len(xs) < lookback + 1:
        raise ValueError("insufficient prices")
    xs = xs[-(lookback + 1):]
    direction = abs(xs[-1] - xs[0])
    noise = sum(abs(b-a) for a,b in zip(xs, xs[1:]))
    return 0.0 if noise <= EPS else direction / noise

def external_capital_score(components: dict[str, float], weights: dict[str, float] | None = None) -> float:
    if not components:
        return 50.0
    weights = weights or {k: 1.0 for k in components}
    denom = sum(abs(weights.get(k, 0.0)) for k in components) or 1.0
    # Inputs are expected z-scores. Map roughly -2..+2 to 0..100.
    z = sum(weights.get(k, 0.0) * float(v) for k,v in components.items()) / denom
    return max(0.0, min(100.0, 50.0 + 25.0 * z))

def control_proxy(concentrated_supply: float, effective_tradable_float: float) -> float:
    if effective_tradable_float <= 0:
        raise ValueError("effective_tradable_float must be positive")
    ratio = max(0.0, concentrated_supply) / effective_tradable_float
    return max(0.0, min(100.0, 100.0 * ratio))

def test_response(delta_order_flow: float, delta_price_pct: float) -> float:
    return float(delta_order_flow) / (abs(float(delta_price_pct)) + EPS)

def capital_efficiency(delta_price_pct: float, net_capital_inflow: float) -> float:
    return float(delta_price_pct) / (abs(float(net_capital_inflow)) + EPS)

def cycle_prior(hours_since_state_change: float, half_life_hours: float = 336.0) -> float:
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    return 100.0 * exp(-0.6931471805599453 * max(0.0, hours_since_state_change) / half_life_hours)

def percentile_rank(value: float, history: Sequence[float]) -> float:
    xs = [float(x) for x in history]
    if not xs:
        return 0.5
    return sum(x <= value for x in xs) / len(xs)
