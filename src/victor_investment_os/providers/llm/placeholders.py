from __future__ import annotations

from typing import Any

from ...interfaces import LLMProvider


class _UnconfiguredProvider(LLMProvider):
    provider_id = "unconfigured"

    def generate_structured(self, *, system_prompt: str, payload: dict[str, Any], response_schema: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Real provider integration is intentionally deferred to Phase 2")


class GeminiProvider(_UnconfiguredProvider):
    provider_id = "gemini-placeholder"


class OpenAIProvider(_UnconfiguredProvider):
    provider_id = "openai-placeholder"

