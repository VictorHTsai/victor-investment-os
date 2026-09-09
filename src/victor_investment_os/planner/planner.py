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
        return (a.symbol, a.asset_type, a.exchange, a.currency, r.dataset_type,
                r.frequency, r.normalization, r.requested_end_date,
                r.trading_calendar_type)

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
            optional_fields = frozenset().union(*(r.optional_fields for r in group)) - fields
            consumers = tuple(sorted({r.requester for r in group}))
            proxy = max(group, key=lambda r: self._PROXY_STRICTNESS[r.proxy_policy]).proxy_policy
            start_dates = [r.requested_start_date for r in group if r.requested_start_date]
            requested_start = min(start_dates) if start_dates else None
            lookback_bars = max((r.lookback_bars or 0 for r in group), default=0) or None
            context_years = max((r.historical_context_years or 0 for r in group), default=0) or None
            identity = (key, sorted(fields), sorted(optional_fields), requested_start,
                        lookback_bars, context_years)
            digest = hashlib.sha256(repr(identity).encode()).hexdigest()[:16]
            planned.append(PlannedDataRequest(
                request_key=f"data-{digest}", asset=first.asset,
                dataset_type=first.dataset_type, frequency=first.frequency,
                lookback_days=max(r.lookback_days for r in group),
                minimum_observations=max(r.minimum_observations for r in group),
                required_fields=fields,
                max_age_seconds=min(r.max_age_seconds for r in group),
                proxy_policy=proxy, normalization=first.normalization,
                consumers=consumers,
                lookback_bars=lookback_bars,
                requested_start_date=requested_start,
                requested_end_date=first.requested_end_date,
                optional_fields=optional_fields,
                historical_context_years=context_years,
                trading_calendar_type=first.trading_calendar_type,
            ))
        return sorted(planned, key=lambda x: x.request_key)
