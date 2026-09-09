from __future__ import annotations

import hashlib

from ..models import DataRequirement, PlannedDataRequest


class IncompatibleRequestError(ValueError):
    pass


class DataRequestPlanner:
    """Merges requirements only when their identity dimensions are compatible."""

    _PROXY_STRICTNESS = {"ALLOW": 0, "ALLOW_WITH_WARNING": 1, "DISALLOW": 2}

    @staticmethod
    def _group_key(r: DataRequirement) -> tuple:
        a = r.asset
        return (a.symbol, a.asset_type, a.exchange, a.currency, r.dataset_type, r.frequency, r.normalization)

    def plan(self, requirements: list[DataRequirement]) -> list[PlannedDataRequest]:
        groups: dict[tuple, list[DataRequirement]] = {}
        for requirement in requirements:
            if requirement.proxy_policy not in self._PROXY_STRICTNESS:
                raise IncompatibleRequestError(f"Unknown proxy policy: {requirement.proxy_policy}")
            groups.setdefault(self._group_key(requirement), []).append(requirement)

        planned: list[PlannedDataRequest] = []
        for key, group in groups.items():
            first = group[0]
            fields = frozenset().union(*(r.required_fields for r in group))
            consumers = tuple(sorted({r.requester for r in group}))
            proxy = max(group, key=lambda r: self._PROXY_STRICTNESS[r.proxy_policy]).proxy_policy
            digest = hashlib.sha256(repr((key, sorted(fields))).encode()).hexdigest()[:16]
            planned.append(PlannedDataRequest(
                request_key=f"data-{digest}", asset=first.asset,
                dataset_type=first.dataset_type, frequency=first.frequency,
                lookback_days=max(r.lookback_days for r in group),
                minimum_observations=max(r.minimum_observations for r in group),
                required_fields=fields,
                max_age_seconds=min(r.max_age_seconds for r in group),
                proxy_policy=proxy, normalization=first.normalization,
                consumers=consumers,
            ))
        return sorted(planned, key=lambda x: x.request_key)

