from __future__ import annotations

from ..interfaces import SourceAdapter
from ..models import PlannedDataRequest


class SourceRouter:
    """Capability-first routing. Source tier is provenance, not route priority."""

    def __init__(self, adapters: list[SourceAdapter]):
        self.adapters = list(adapters)

    def route(self, request: PlannedDataRequest) -> list[SourceAdapter]:
        compatible = [adapter for adapter in self.adapters if adapter.supports(request)]
        return sorted(compatible, key=lambda adapter: (adapter.routing_priority(request), adapter.adapter_id))

