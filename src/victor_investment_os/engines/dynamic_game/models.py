from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Mapping

STATES = ("accumulation", "test", "shakeout", "markup", "distribution", "neutral")
FACTORS = ("R", "L", "F", "C", "P", "V", "D", "E", "T")

def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(x)))

@dataclass(frozen=True)
class FactorVector:
    R: float; L: float; F: float; C: float; P: float
    V: float; D: float; E: float; T: float
    def __post_init__(self):
        for k in FACTORS:
            object.__setattr__(self, k, _clip(getattr(self, k)))
    def as_dict(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in FACTORS}

@dataclass(frozen=True)
class DGEInput:
    symbol: str
    as_of: str
    factors: FactorVector
    provenance: Mapping[str, str] = field(default_factory=dict)
    # Optional normalized observations. Values should be in [-1,1] unless noted.
    observations: Mapping[str, float] = field(default_factory=dict)

@dataclass(frozen=True)
class StateProbabilities:
    accumulation: float; test: float; shakeout: float
    markup: float; distribution: float; neutral: float
    def as_dict(self) -> dict[str, float]:
        return {s: getattr(self, s) for s in STATES}

@dataclass(frozen=True)
class DGEOutput:
    schema_version: str
    symbol: str
    as_of: str
    factors: FactorVector
    states: StateProbabilities
    dominant_state: str
    confidence: float
    expected_next_observations: tuple[str, ...]
    invalidators: tuple[str, ...]
    provenance: Mapping[str, str]
    methodology: str = "DGE_V1_RULE_BASED_BASELINE"
    def to_dict(self) -> dict:
        d = asdict(self)
        return d
