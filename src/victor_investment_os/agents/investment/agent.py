from __future__ import annotations

from ...interfaces import InvestmentAgent, LLMProvider
from ...models import ComponentResult, FailureCode, RequestEnvelope


class SpecializedInvestmentAgent(InvestmentAgent):
    name = "investment_agent"

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def assess(self, request: RequestEnvelope, engine_outputs: dict[str, ComponentResult]) -> ComponentResult:
        successful = {k: v.output for k, v in engine_outputs.items() if v.status == "SUCCESS" and v.output}
        if "setup" not in successful:
            return ComponentResult.failed(self.name, FailureCode.DEPENDENCY_FAILED, "Setup output is required")
        payload = {"request": {"request_id": request.request_id, "asset": request.asset.symbol},
                   "engine_outputs": successful}
        try:
            output = self.provider.generate_structured(
                system_prompt=("Reason only across supplied structured outputs. Never invent missing data, "
                               "never recalculate indicators, and distinguish opportunity from action."),
                payload=payload, response_schema={"$ref": "contracts/v1/investment_agent.schema.json"},
            )
            if output.get("action_triggered") and output.get("assessment_state") != "TRIGGERED":
                return ComponentResult.failed(self.name, FailureCode.VALIDATION_FAILED,
                                              "action_triggered conflicts with assessment_state")
            return ComponentResult.success(self.name, output)
        except Exception as exc:
            return ComponentResult.failed(self.name, FailureCode.AGENT_FAILED, str(exc))

