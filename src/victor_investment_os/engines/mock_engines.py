from __future__ import annotations

from typing import Any

from ..interfaces import (
    CompressionEngine, ExpectationGapEngine, MacroThesisEngine, SetupEngine, TechnicalEngine,
)
from ..models import (
    ComponentResult, DataRequirement, Dataset, FailureCode, RequestEnvelope, SetupState, to_dict,
)


def _ohlcv_requirement(name: str, request: RequestEnvelope, *, lookback: int, minimum: int, fields: set[str]) -> DataRequirement:
    return DataRequirement(name, request.asset, "OHLCV", "1d", lookback, minimum,
                           frozenset(fields), max_age_seconds=86_400,
                           proxy_policy="DISALLOW", normalization="SPLIT_ADJUSTED")


def _mock_provenance(datasets: dict[str, Dataset]) -> list[dict[str, Any]]:
    return [to_dict(dataset.provenance) for dataset in datasets.values()]


class MockCompressionEngine(CompressionEngine):
    name = "compression"

    def requirements(self, request: RequestEnvelope) -> list[DataRequirement]:
        return [_ohlcv_requirement(self.name, request, lookback=756, minimum=500,
                                   fields={"high", "low", "close", "volume"})]

    def run(self, request, datasets, upstream):
        if not datasets:
            return ComponentResult.failed(self.name, FailureCode.INSUFFICIENT_DATA, "OHLCV dataset missing")
        return ComponentResult.success(self.name, {
            "is_mock": True, "overall_score": 72, "classification": "MOCK_COMPRESSION_PRESENT",
            "component_scores": {"mock_range": 70, "mock_volatility": 74},
            "historical_percentiles": {"mock_compression": 82},
            "score_trend": "MOCK_STABLE", "primary_drivers": ["Mock range contraction"],
            "confidence": 0.60, "provenance": _mock_provenance(datasets),
        })


class MockTechnicalEngine(TechnicalEngine):
    name = "technical"

    def requirements(self, request: RequestEnvelope) -> list[DataRequirement]:
        return [_ohlcv_requirement(self.name, request, lookback=1260, minimum=750,
                                   fields={"open", "high", "low", "close", "volume"})]

    def run(self, request, datasets, upstream):
        if not datasets:
            return ComponentResult.failed(self.name, FailureCode.INSUFFICIENT_DATA, "OHLCV dataset missing")
        return ComponentResult.success(self.name, {
            "is_mock": True, "overall_score": 64, "trend": "MOCK_UPTREND",
            "structure": "MOCK_CONSOLIDATION", "support": [27.0], "resistance": [31.0],
            "breakout_state": "NOT_CONFIRMED", "trigger": "Mock close above 31.0",
            "invalidation": "Mock close below 27.0", "momentum": "MOCK_NEUTRAL",
            "confidence": 0.58, "provenance": _mock_provenance(datasets),
        })


class MockExpectationGapEngine(ExpectationGapEngine):
    name = "expectation_gap"

    def requirements(self, request: RequestEnvelope) -> list[DataRequirement]:
        return []

    def run(self, request, datasets, upstream):
        return ComponentResult.success(self.name, {
            "is_mock": True, "status": "METHODOLOGY_NOT_IMPLEMENTED",
            "market_expectation": "MOCK_UNSPECIFIED", "thesis_expectation": "MOCK_UNSPECIFIED",
            "gap_direction": "UNKNOWN", "confidence": 0.20,
            "missing_inputs": ["consensus", "forward assumptions", "narrative evidence"],
            "provenance": [],
        }, ["Phase 1 interface mock; no expectation-gap methodology applied"])


class MockMacroThesisEngine(MacroThesisEngine):
    name = "macro_thesis"

    def requirements(self, request: RequestEnvelope) -> list[DataRequirement]:
        return []

    def run(self, request, datasets, upstream):
        return ComponentResult.success(self.name, {
            "is_mock": True, "status": "METHODOLOGY_NOT_IMPLEMENTED",
            "structural_drivers": ["MOCK_DRIVER"], "cycle_context": "MOCK_UNKNOWN",
            "bull_case": "Mock bull-case placeholder", "base_case": "Mock base-case placeholder",
            "bear_case": "Mock bear-case placeholder",
            "invalidation_conditions": ["Requires Phase 2 methodology"],
            "confidence": 0.20, "provenance": [],
        }, ["Phase 1 interface mock; no macro-thesis methodology applied"])


class MockSetupEngine(SetupEngine):
    name = "setup"

    def requirements(self, request: RequestEnvelope) -> list[DataRequirement]:
        return []

    def run(self, request, datasets, upstream):
        available = {k: v.output for k, v in upstream.items() if v.status == "SUCCESS" and v.output}
        if not available:
            return ComponentResult.failed(self.name, FailureCode.DEPENDENCY_FAILED, "No intelligence engine output available")
        missing = sorted(set(upstream) - set(available))
        # Explicit fixture logic only: these values are not an investment formula.
        output = {
            "is_mock": True, "mock_logic_id": "PHASE1_FIXED_FIXTURE_V1",
            "opportunity_score": 68, "setup_state": SetupState.WATCH.value,
            "trigger": available.get("technical", {}).get("trigger"),
            "invalidation": available.get("technical", {}).get("invalidation"),
            "engine_snapshot": available, "missing_engines": missing,
            "confidence": 0.45 if missing else 0.55,
        }
        warnings = [f"Partial setup: missing {', '.join(missing)}"] if missing else []
        warnings.append("Opportunity score is a mock fixture and is separate from setup state")
        return ComponentResult.success(self.name, output, warnings)
