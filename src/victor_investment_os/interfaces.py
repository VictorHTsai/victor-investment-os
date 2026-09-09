from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import ComponentResult, DataRequirement, Dataset, PlannedDataRequest, RequestEnvelope


class RequirementDeclarer(ABC):
    name: str

    @abstractmethod
    def requirements(self, request: RequestEnvelope) -> list[DataRequirement]: ...


class IntelligenceEngine(RequirementDeclarer):
    @abstractmethod
    def run(self, request: RequestEnvelope, datasets: dict[str, Dataset], upstream: dict[str, ComponentResult]) -> ComponentResult: ...


class CompressionEngine(IntelligenceEngine):
    """Deterministic compression-engine boundary."""


class TechnicalEngine(IntelligenceEngine):
    """Deterministic technical-engine boundary."""


class ExpectationGapEngine(IntelligenceEngine):
    """Hybrid boundary; bounded semantic workers may be added behind it."""


class MacroThesisEngine(IntelligenceEngine):
    """Hybrid boundary; bounded semantic workers may be added behind it."""


class SetupEngine(IntelligenceEngine):
    """Consumes structured intelligence outputs, never raw market data."""


class SourceAdapter(ABC):
    adapter_id: str
    priority: int = 100

    @abstractmethod
    def supports(self, request: PlannedDataRequest) -> bool: ...

    @abstractmethod
    def retrieve(self, request: PlannedDataRequest) -> Dataset: ...


class DataWorker(ABC):
    @abstractmethod
    def retrieve(self, request: PlannedDataRequest) -> Dataset | Any: ...


class LLMProvider(ABC):
    provider_id: str

    @abstractmethod
    def generate_structured(self, *, system_prompt: str, payload: dict[str, Any], response_schema: dict[str, Any]) -> dict[str, Any]: ...


class InvestmentAgent(ABC):
    name: str

    @abstractmethod
    def assess(self, request: RequestEnvelope, engine_outputs: dict[str, ComponentResult]) -> ComponentResult: ...
