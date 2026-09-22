from __future__ import annotations
from math import exp
from .models import DGEInput, DGEOutput, StateProbabilities, STATES

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))

def _n(x: float) -> float:
    return (float(x) - 50.0) / 50.0

def _softmax(scores: dict[str, float]) -> dict[str, float]:
    m = max(scores.values())
    ex = {k: exp(v-m) for k,v in scores.items()}
    z = sum(ex.values())
    return {k: v/z for k,v in ex.items()}

class DynamicGameEngine:
    """Deterministic DGE V1 baseline.

    It deliberately does NOT infer a literal market-maker identity or intent.
    It maps public proxies to falsifiable latent-state probabilities.
    """

    schema_version = "dge.v1"

    def analyze(self, x: DGEInput) -> DGEOutput:
        f = x.factors
        o = {k: float(v) for k,v in x.observations.items()}
        R,L,F,C,P,V,D,E,T = (_n(getattr(f,k)) for k in ("R","L","F","C","P","V","D","E","T"))
        reclaim = o.get("reclaim", 0.0)
        spot = o.get("spot_cvd", 0.0)
        oi_flush = o.get("oi_flush", 0.0)
        supply = o.get("supply_pressure", 0.0)
        capital_eff = o.get("capital_efficiency", 0.0)
        shock = o.get("shock", 0.0)

        scores = {
            "accumulation": 0.70*P + 0.45*C + 0.30*L - 0.35*D + 0.25*spot,
            "test": 0.80*V + 0.40*oi_flush + 0.35*abs(shock) + 0.25*reclaim,
            "shakeout": 0.55*V + 0.45*P + 0.35*oi_flush + 0.35*reclaim - 0.30*supply,
            "markup": 0.70*F + 0.45*L + 0.40*reclaim + 0.35*spot + 0.20*R - 0.35*D,
            "distribution": 0.60*D + 0.45*supply + 0.35*F - 0.55*capital_eff + 0.20*C,
            "neutral": 0.35*(1-abs(R)) + 0.20*(1-abs(F)) + 0.20*(1-abs(V)) + 0.15*T,
        }
        # High abnormal-event pressure flattens state certainty instead of pretending old regime survives.
        if f.E >= 75 or abs(shock) >= 0.8:
            avg = sum(scores.values()) / len(scores)
            scores = {k: 0.55*v + 0.45*avg for k,v in scores.items()}
            scores["neutral"] += 0.35

        probs = _softmax(scores)
        dominant = max(probs, key=probs.get)
        confidence = probs[dominant]
        next_obs, invalidators = self._explain(dominant)
        return DGEOutput(
            schema_version=self.schema_version, symbol=x.symbol, as_of=x.as_of,
            factors=f,
            states=StateProbabilities(**probs),
            dominant_state=dominant, confidence=confidence,
            expected_next_observations=next_obs, invalidators=invalidators,
            provenance=dict(x.provenance),
        )

    @staticmethod
    def _explain(state: str) -> tuple[tuple[str,...], tuple[str,...]]:
        mapping = {
            "accumulation": (("downside selling response weakens", "reclaim after downside test"), ("spot selling accelerates", "exchange inflow/supply pressure expands")),
            "test": (("observe spot selling elasticity", "observe OI/liquidation flush and reclaim"), ("shock creates persistent spot selling",)),
            "shakeout": (("next comparable shock has lower marginal sell response",), ("marginal sell response re-accelerates",)),
            "markup": (("spot CVD confirms breakout", "external capital remains positive"), ("breakout loses equilibrium", "leverage overheats without spot confirmation")),
            "distribution": (("capital inflow produces less price response", "supply pressure persists"), ("price elasticity recovers while supply pressure falls",)),
            "neutral": (("wait for discriminating observation",), ("none: low confidence is the state",)),
        }
        return mapping[state]
