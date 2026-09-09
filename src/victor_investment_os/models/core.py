from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrEnum(str, Enum):
    pass


class DataClassification(StrEnum):
    DIRECT = "DIRECT"
    RECONSTRUCTED = "RECONSTRUCTED"
    PROXY = "PROXY"
    INFERRED = "INFERRED"
    UNAVAILABLE = "UNAVAILABLE"


class SourceTier(StrEnum):
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"
    TIER_4 = "TIER_4"
    TIER_5 = "TIER_5"


class AdjustmentPolicy(StrEnum):
    RAW = "RAW"
    SPLIT_ADJUSTED = "SPLIT_ADJUSTED"
    SPLIT_DIVIDEND_ADJUSTED = "SPLIT_DIVIDEND_ADJUSTED"
    PROVIDER_ADJUSTED = "PROVIDER_ADJUSTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class TradingCalendarType(StrEnum):
    US_EQUITY_SESSIONS = "US_EQUITY_SESSIONS"
    CONTINUOUS_24_7 = "CONTINUOUS_24_7"
    UNKNOWN = "UNKNOWN"


class FailureCode(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    SOURCE_FAILURE = "SOURCE_FAILURE"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    DEPENDENCY_FAILED = "DEPENDENCY_FAILED"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    ENGINE_FAILED = "ENGINE_FAILED"
    AGENT_FAILED = "AGENT_FAILED"


class SetupState(StrEnum):
    IGNORE = "IGNORE"
    WATCH = "WATCH"
    SETUP = "SETUP"
    TRIGGERED = "TRIGGERED"


@dataclass(frozen=True)
class Asset:
    symbol: str
    asset_type: str
    exchange: str
    currency: str


@dataclass(frozen=True)
class RequestEnvelope:
    contract_version: str
    request_id: str
    analysis_as_of: str
    asset: Asset
    mode: str = "live"


@dataclass(frozen=True)
class DataRequirement:
    requester: str
    asset: Asset
    dataset_type: str
    frequency: str
    lookback_days: int
    minimum_observations: int
    required_fields: frozenset[str]
    max_age_seconds: int
    proxy_policy: str = "DISALLOW"
    normalization: str = "RAW"
    # Phase 2 additions. lookback_days remains as a deprecated compatibility field.
    lookback_bars: int | None = None
    requested_start_date: str | None = None
    requested_end_date: str | None = None
    optional_fields: frozenset[str] = frozenset()
    historical_context_years: int | None = None
    trading_calendar_type: str | None = None


@dataclass(frozen=True)
class PlannedDataRequest:
    request_key: str
    asset: Asset
    dataset_type: str
    frequency: str
    lookback_days: int
    minimum_observations: int
    required_fields: frozenset[str]
    max_age_seconds: int
    proxy_policy: str
    normalization: str
    consumers: tuple[str, ...]
    lookback_bars: int | None = None
    requested_start_date: str | None = None
    requested_end_date: str | None = None
    optional_fields: frozenset[str] = frozenset()
    historical_context_years: int | None = None
    trading_calendar_type: str | None = None


@dataclass
class Provenance:
    source_id: str
    source_name: str
    source_tier: str
    retrieved_at: str
    source_timestamp: str
    data_type: str
    transformations: list[str] = field(default_factory=list)
    confidence: float | None = None
    adjustment_policy: str = AdjustmentPolicy.UNKNOWN.value


@dataclass
class DatasetMetadata:
    symbol: str
    asset_type: str
    currency: str
    frequency: str
    trading_calendar_type: str
    adjustment_policy: str
    requested_start_date: str | None = None
    requested_end_date: str | None = None
    actual_start_date: str | None = None
    actual_end_date: str | None = None
    actual_observation_count: int = 0
    requested_lookback_bars: int | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class Dataset:
    request_key: str
    records: list[dict[str, Any]]
    provenance: Provenance
    is_mock: bool = False
    metadata: DatasetMetadata | None = None


@dataclass
class ComponentFailure:
    component: str
    code: str
    message: str
    recoverable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentResult:
    component: str
    status: str
    output: dict[str, Any] | None = None
    failure: ComponentFailure | None = None
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def success(cls, component: str, output: dict[str, Any], warnings: list[str] | None = None):
        return cls(component, "SUCCESS", output, warnings=warnings or [])

    @classmethod
    def failed(cls, component: str, code: FailureCode, message: str, recoverable: bool = False):
        return cls(component, "FAILED", failure=ComponentFailure(component, code.value, message, recoverable))


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {k: to_dict(v) for k, v in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        return [to_dict(v) for v in sorted(value)]
    if isinstance(value, tuple):
        return [to_dict(v) for v in value]
    if isinstance(value, dict):
        return {k: to_dict(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_dict(v) for v in value]
    return value
