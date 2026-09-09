from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite

from ..models import PlannedDataRequest


@dataclass
class OHLCVValidationReport:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    volume_available: bool = True


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_ohlcv(records: list[dict], request: PlannedDataRequest) -> OHLCVValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    if len(records) < request.minimum_observations:
        errors.append(f"requires {request.minimum_observations} observations; got {len(records)}")

    timestamps: list[datetime] = []
    volume_available = True
    required = set(request.required_fields)
    for index, row in enumerate(records):
        missing = required - row.keys()
        if missing:
            errors.append(f"record {index} missing fields: {sorted(missing)}")
            continue
        try:
            timestamps.append(_parse_timestamp(row.get("timestamp")))
        except (TypeError, ValueError) as exc:
            errors.append(f"record {index} invalid timestamp: {exc}")

        values: dict[str, float] = {}
        for field_name in ("open", "high", "low", "close"):
            value = row.get(field_name)
            if value is None:
                errors.append(f"record {index} missing {field_name}")
                continue
            try:
                number = float(value)
                if not isfinite(number) or number <= 0:
                    raise ValueError
                values[field_name] = number
            except (TypeError, ValueError):
                errors.append(f"record {index} {field_name} must be finite and positive")
        if len(values) == 4:
            if values["high"] < values["low"]:
                errors.append(f"record {index} high below low")
            if values["high"] < max(values["open"], values["close"]):
                errors.append(f"record {index} high below open/close")
            if values["low"] > min(values["open"], values["close"]):
                errors.append(f"record {index} low above open/close")

        volume = row.get("volume")
        if volume is None:
            volume_available = False
        else:
            try:
                number = float(volume)
                if not isfinite(number) or number < 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"record {index} volume must be finite and non-negative")

    if len(timestamps) == len(records):
        if len(set(timestamps)) != len(timestamps):
            errors.append("duplicate timestamps")
        if any(left >= right for left, right in zip(timestamps, timestamps[1:])):
            errors.append("timestamps must be strictly increasing")
    if not volume_available:
        if "volume" in required:
            errors.append("required volume is unavailable")
        else:
            warnings.append("Volume is unavailable for one or more bars")
    return OHLCVValidationReport(not errors, errors, warnings, volume_available)

