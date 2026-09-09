from victor_investment_os.data.adapters import MockMarketDataAdapter
from victor_investment_os.example import run_slv_example
from victor_investment_os.interfaces import LLMProvider
from victor_investment_os.models import Asset, DataRequirement, RequestEnvelope
from victor_investment_os.orchestrator import build_phase1_orchestrator
from victor_investment_os.planner import DataRequestPlanner
from victor_investment_os.providers.llm import MockLLMProvider


def request():
    return RequestEnvelope("1.0", "test", "2026-09-09T00:00:00Z", Asset("SLV", "ETF", "NYSEARCA", "USD"))


def test_missing_data_becomes_structured_partial_failure():
    result = build_phase1_orchestrator(adapter=MockMarketDataAdapter(fail=True)).analyze(request())
    assert result["execution"]["data_failures"][0]["code"] == "SOURCE_FAILURE"
    assert result["execution"]["component_status"]["compression"] == "FAILED"
    assert result["execution"]["component_status"]["technical"] == "FAILED"
    assert result["execution"]["component_status"]["setup"] == "SUCCESS"
    assert result["assessment"]["assessment_state"] == "WATCH"


def test_provider_abstraction_accepts_another_implementation():
    assert isinstance(MockLLMProvider(), LLMProvider)

    class AlternateProvider(LLMProvider):
        provider_id = "alternate"
        def generate_structured(self, **kwargs):
            return MockLLMProvider().generate_structured(**kwargs)

    result = build_phase1_orchestrator(provider=AlternateProvider()).analyze(request())
    assert result["assessment"]["is_mock"] is True


def test_end_to_end_mock_slv_pipeline():
    result = run_slv_example()
    assert result["is_mock"] is True
    assert result["asset"]["symbol"] == "SLV"
    assert len(result["execution"]["planned_data_requests"]) == 1
    planned = result["execution"]["planned_data_requests"][0]
    assert planned["lookback_days"] == 1260
    assert set(planned["consumers"]) == {"compression", "technical"}
    assert result["assessment"]["assessment_state"] == "WATCH"
    assert result["assessment"]["action_triggered"] is False
    assert result["assessment"]["opportunity_score"] == 68

