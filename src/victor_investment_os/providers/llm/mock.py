from __future__ import annotations

from typing import Any

from ...interfaces import LLMProvider


class MockLLMProvider(LLMProvider):
    provider_id = "mock-llm"

    def generate_structured(self, *, system_prompt: str, payload: dict[str, Any], response_schema: dict[str, Any]) -> dict[str, Any]:
        setup = payload["engine_outputs"].get("setup", {})
        snapshot = setup.get("engine_snapshot", {})
        return {
            "is_mock": True,
            "assessment_state": setup.get("setup_state", "WATCH"),
            "opportunity_score": setup.get("opportunity_score", 0),
            "action_triggered": setup.get("setup_state") == "TRIGGERED",
            "confidence": setup.get("confidence", 0.0),
            "one_line_thesis": "MOCK: Compression may be interesting, but the technical trigger is not confirmed.",
            "supporting_evidence": ["Mock compression output reports elevated compression"],
            "contradicting_evidence": ["Mock technical breakout state is NOT_CONFIRMED"],
            "bull_case": snapshot.get("macro_thesis", {}).get("bull_case", "Unavailable"),
            "bear_case": snapshot.get("macro_thesis", {}).get("bear_case", "Unavailable"),
            "trigger": setup.get("trigger"), "invalidation": setup.get("invalidation"),
            "missing_intelligence": snapshot.get("expectation_gap", {}).get("missing_inputs", []),
            "conflicts": [], "current_action": "WATCH; do not treat mock output as investment advice",
            "next_research_step": "Define Phase 2 methodologies and connect validated evidence sources",
        }

