from __future__ import annotations

from typing import Iterable

from ..agents.investment import SpecializedInvestmentAgent
from ..data.adapters import MockMarketDataAdapter
from ..data.worker import DataRetrievalWorker
from ..engines import (
    MockCompressionEngine, MockExpectationGapEngine, MockMacroThesisEngine,
    MockSetupEngine, MockTechnicalEngine,
)
from ..interfaces import IntelligenceEngine
from ..models import ComponentFailure, ComponentResult, Dataset, RequestEnvelope, to_dict
from ..planner import DataRequestPlanner
from ..providers.llm import MockLLMProvider
from .dag import DAGExecutor, Node


class Orchestrator:
    """Deterministic control plane; graph topology is declared, not embedded in execution order."""

    def __init__(self, *, engines: Iterable[IntelligenceEngine], setup_engine: IntelligenceEngine,
                 investment_agent: SpecializedInvestmentAgent, planner: DataRequestPlanner,
                 worker: DataRetrievalWorker, dag_executor: DAGExecutor | None = None):
        self.engines = {engine.name: engine for engine in engines}
        self.setup_engine = setup_engine
        self.investment_agent = investment_agent
        self.planner = planner
        self.worker = worker
        self.dag_executor = dag_executor or DAGExecutor()

    def analyze(self, request: RequestEnvelope) -> dict:
        requirements = [req for engine in self.engines.values() for req in engine.requirements(request)]
        planned = self.planner.plan(requirements)
        datasets_by_consumer: dict[str, dict[str, Dataset]] = {name: {} for name in self.engines}
        data_failures: list[ComponentFailure] = []
        for data_request in planned:
            result = self.worker.retrieve(data_request)
            if isinstance(result, ComponentFailure):
                data_failures.append(result)
                continue
            for consumer in data_request.consumers:
                datasets_by_consumer.setdefault(consumer, {})[data_request.request_key] = result

        nodes: dict[str, Node] = {}
        for name, engine in self.engines.items():
            nodes[name] = Node(name, frozenset(),
                lambda upstream, e=engine, n=name: e.run(request, datasets_by_consumer.get(n, {}), upstream))

        engine_names = frozenset(self.engines)
        nodes[self.setup_engine.name] = Node(
            self.setup_engine.name, engine_names,
            lambda upstream: self.setup_engine.run(request, {}, upstream), allow_partial=True)
        nodes[self.investment_agent.name] = Node(
            self.investment_agent.name, frozenset({self.setup_engine.name}),
            lambda upstream: self.investment_agent.assess(request, upstream))

        results, levels = self.dag_executor.execute(nodes)
        assessment = results[self.investment_agent.name]
        return {
            "contract_version": request.contract_version,
            "request_id": request.request_id,
            "analysis_as_of": request.analysis_as_of,
            "asset": to_dict(request.asset), "mode": request.mode,
            "is_mock": True,
            "execution": {
                "levels": levels,
                "planned_data_requests": [to_dict(item) for item in planned],
                "data_failures": [to_dict(item) for item in data_failures],
                "component_status": {name: result.status for name, result in results.items()},
                "warnings": [warning for result in results.values() for warning in result.warnings],
            },
            "assessment": assessment.output,
            "failures": [to_dict(r.failure) for r in results.values() if r.failure],
        }


def build_phase1_orchestrator(*, adapter: MockMarketDataAdapter | None = None,
                              provider: MockLLMProvider | None = None) -> Orchestrator:
    return Orchestrator(
        engines=[MockCompressionEngine(), MockTechnicalEngine(),
                 MockExpectationGapEngine(), MockMacroThesisEngine()],
        setup_engine=MockSetupEngine(),
        investment_agent=SpecializedInvestmentAgent(provider or MockLLMProvider()),
        planner=DataRequestPlanner(),
        worker=DataRetrievalWorker([adapter or MockMarketDataAdapter()]),
    )

