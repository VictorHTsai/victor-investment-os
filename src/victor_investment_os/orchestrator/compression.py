from __future__ import annotations

from ..data.adapters import AlpacaMarketDataAdapter, CoinbaseExchangeAdapter, YahooChartAdapter
from ..data.router import SourceRouter
from ..data.worker import DataRetrievalWorker
from ..engines.compression import CompressionEngineV1
from ..models import ComponentFailure, RequestEnvelope, to_dict
from ..planner import DataRequestPlanner


class CompressionAnalysisOrchestrator:
    """Phase 2 dependency slice: planner -> worker/router -> Compression V1."""

    def __init__(self, engine: CompressionEngineV1, planner: DataRequestPlanner,
                 worker: DataRetrievalWorker):
        self.engine = engine
        self.planner = planner
        self.worker = worker

    def analyze(self, request: RequestEnvelope) -> dict:
        planned = self.planner.plan(self.engine.requirements(request))
        datasets = {}
        failures = []
        for item in planned:
            result = self.worker.retrieve(item)
            if isinstance(result, ComponentFailure):
                failures.append(result)
            else:
                datasets[item.request_key] = result
        if failures:
            return {
                "contract_version": request.contract_version, "request_id": request.request_id,
                "engine": self.engine.name, "engine_version": self.engine.engine_version,
                "asset": to_dict(request.asset), "analysis_as_of": request.analysis_as_of,
                "status": "UNAVAILABLE", "is_mock": False,
                "failures": [to_dict(item) for item in failures],
                "planned_data_requests": [to_dict(item) for item in planned],
            }
        result = self.engine.run(request, datasets, {})
        if result.status != "SUCCESS":
            return {
                "contract_version": request.contract_version, "request_id": request.request_id,
                "engine": self.engine.name, "engine_version": self.engine.engine_version,
                "asset": to_dict(request.asset), "analysis_as_of": request.analysis_as_of,
                "status": "INVALID", "is_mock": False,
                "failures": [to_dict(result.failure)] if result.failure else [],
                "planned_data_requests": [to_dict(item) for item in planned],
            }
        return result.output or {}


def build_phase2_compression_orchestrator() -> CompressionAnalysisOrchestrator:
    router = SourceRouter([
        CoinbaseExchangeAdapter(),
        AlpacaMarketDataAdapter(),
        YahooChartAdapter(),
    ])
    return CompressionAnalysisOrchestrator(
        CompressionEngineV1(), DataRequestPlanner(), DataRetrievalWorker(router=router)
    )

