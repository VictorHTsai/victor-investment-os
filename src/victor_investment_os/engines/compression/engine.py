from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import log, sqrt
from statistics import fmean, pstdev
from typing import Any

from ...interfaces import CompressionEngine
from ...models import (
    AdjustmentPolicy, ComponentResult, DataRequirement, Dataset, FailureCode,
    RequestEnvelope, TradingCalendarType, to_dict,
)
from ...data.validation import validate_ohlcv


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _minus_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:  # February 29
        return value.replace(year=value.year - years, day=28)


def percentile_rank(values: list[float], score: float) -> float | None:
    """Inclusive average rank: minimum=0, maximum=1, ties use average rank."""
    if len(values) < 2:
        return None
    ordered = sorted(values)
    left = bisect_left(ordered, score)
    right = bisect_right(ordered, score)
    average_zero_based_rank = (left + right - 1) / 2
    return average_zero_based_rank / (len(ordered) - 1)


@dataclass(frozen=True)
class CompressionConfig:
    feature_windows: tuple[int, ...] = (20, 60, 126, 252)
    bollinger_stddevs: float = 2.0
    volume_short_window: int = 20
    volume_long_window: int = 60
    primary_context_years: int = 5
    secondary_context_years: int = 3
    retrieval_warmup_calendar_years: int = 2
    context_min_density: float = 0.80
    context_start_tolerance_days_equity: int = 10
    context_start_tolerance_days_crypto: int = 2


class CompressionEngineV1(CompressionEngine):
    name = "compression"
    engine_version = "1.0.0"

    def __init__(self, config: CompressionConfig | None = None):
        self.config = config or CompressionConfig()

    def requirements(self, request: RequestEnvelope) -> list[DataRequirement]:
        analysis_date = _dt(request.analysis_as_of).date()
        # Phase 2 conservatively excludes the current potentially incomplete daily bar.
        # TODO(Phase 2.1): replace this date-only rule with provider-aware bar-completion
        # logic using asset calendar, exchange timezone/session close, and timestamp semantics.
        completed_data_end = analysis_date - timedelta(days=1)
        # Extra calendar time supplies 252-bar warm-up plus 20-bar change history.
        requested_start = _minus_years(
            completed_data_end,
            self.config.primary_context_years + self.config.retrieval_warmup_calendar_years,
        )
        is_crypto = request.asset.asset_type.upper() == "CRYPTO"
        calendar_type = (TradingCalendarType.CONTINUOUS_24_7.value if is_crypto
                         else TradingCalendarType.US_EQUITY_SESSIONS.value)
        normalization = (AdjustmentPolicy.NOT_APPLICABLE.value if is_crypto
                         else AdjustmentPolicy.SPLIT_DIVIDEND_ADJUSTED.value)
        max_window = max(max(self.config.feature_windows), self.config.volume_long_window)
        return [DataRequirement(
            requester=self.name, asset=request.asset, dataset_type="OHLCV", frequency="1d",
            # Deprecated compatibility field; adapters use explicit dates + lookback_bars.
            lookback_days=(self.config.primary_context_years
                           + self.config.retrieval_warmup_calendar_years) * 366,
            minimum_observations=max_window + 1,
            required_fields=frozenset({"timestamp", "open", "high", "low", "close"}),
            max_age_seconds=86_400, proxy_policy="DISALLOW", normalization=normalization,
            lookback_bars=max_window, requested_start_date=requested_start.isoformat(),
            requested_end_date=completed_data_end.isoformat(), optional_fields=frozenset({"volume"}),
            historical_context_years=self.config.primary_context_years,
            trading_calendar_type=calendar_type,
        )]

    def run(self, request: RequestEnvelope, datasets: dict[str, Dataset], upstream: dict[str, ComponentResult]) -> ComponentResult:
        if not datasets:
            return ComponentResult.failed(self.name, FailureCode.INSUFFICIENT_DATA, "OHLCV dataset missing")
        dataset = next(iter(datasets.values()))
        requirement = self.requirements(request)[0]
        planned_like = type("PlannedLike", (), {
            "minimum_observations": requirement.minimum_observations,
            "required_fields": requirement.required_fields,
        })()
        validation = validate_ohlcv(dataset.records, planned_like)  # structural compatibility
        if not validation.valid:
            return ComponentResult.failed(
                self.name, FailureCode.VALIDATION_FAILED, "; ".join(validation.errors)
            )
        try:
            output = self.analyze(request, dataset, validation.warnings)
            return ComponentResult.success(self.name, output, output["warnings"])
        except Exception as exc:
            return ComponentResult.failed(self.name, FailureCode.ENGINE_FAILED, str(exc))

    def analyze(self, request: RequestEnvelope, dataset: Dataset,
                validation_warnings: list[str] | None = None) -> dict[str, Any]:
        rows = dataset.records
        dates = [_dt(row["timestamp"]) for row in rows]
        opens = [float(row["open"]) for row in rows]
        highs = [float(row["high"]) for row in rows]
        lows = [float(row["low"]) for row in rows]
        closes = [float(row["close"]) for row in rows]
        volumes = [None if row.get("volume") is None else float(row["volume"]) for row in rows]
        calendar_type = (dataset.metadata.trading_calendar_type if dataset.metadata
                         else self.requirements(request)[0].trading_calendar_type)
        annualization = 365 if calendar_type == TradingCalendarType.CONTINUOUS_24_7.value else 252

        returns: list[float | None] = [None]
        returns.extend(log(closes[i] / closes[i - 1]) for i in range(1, len(closes)))
        true_ranges = [highs[0] - lows[0]]
        true_ranges.extend(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                               abs(lows[i] - closes[i - 1])) for i in range(1, len(rows)))

        features: dict[str, list[dict[str, Any]]] = {
            "realized_volatility": [], "normalized_atr": [],
            "bollinger_band_width": [], "rolling_price_range": [],
            "volume_activity": [],
        }
        for window in self.config.feature_windows:
            rv = self._rolling_realized_volatility(returns, window, annualization)
            atr = self._rolling_normalized_atr(true_ranges, closes, window)
            bbw = self._rolling_bbw(closes, window, self.config.bollinger_stddevs)
            range_pct = self._rolling_range(highs, lows, closes, window)
            features["realized_volatility"].append(
                self._feature_output("realized_volatility", window, rv, dates, calendar_type, True))
            features["normalized_atr"].append(
                self._feature_output("normalized_atr", window, atr, dates, calendar_type, True))
            features["bollinger_band_width"].append(
                self._feature_output("bollinger_band_width", window, bbw, dates, calendar_type, True))
            features["rolling_price_range"].append(
                self._feature_output("rolling_price_range", window, range_pct, dates, calendar_type, True))

        volume_series = self._rolling_volume_activity(
            volumes, self.config.volume_short_window, self.config.volume_long_window
        )
        volume_output = self._feature_output(
            "volume_activity", self.config.volume_long_window, volume_series,
            dates, calendar_type, False,
            parameters={"short_window_bars": self.config.volume_short_window,
                        "long_window_bars": self.config.volume_long_window},
            unavailable=not volume_series or volume_series[-1] is None,
        )
        features["volume_activity"].append(volume_output)

        all_feature_items = [item for family in features.values() for item in family]
        unavailable = [item for item in all_feature_items if item["status"] != "AVAILABLE"]
        warnings = list(validation_warnings or [])
        if dataset.metadata:
            warnings.extend(dataset.metadata.warnings)
        if volume_output["status"] != "AVAILABLE":
            warnings.append("Volume activity unavailable; other compression features remain valid")
        if any(self._has_insufficient_context(item) for item in all_feature_items):
            warnings.append("One or more historical percentile contexts are insufficient")
        warnings = list(dict.fromkeys(warnings))

        data_quality = self._data_quality(dataset, rows, calendar_type, warnings)
        top_status = "PARTIAL" if unavailable or data_quality["quality_status"] != "VALID" else "AVAILABLE"
        return {
            "contract_version": request.contract_version,
            "request_id": request.request_id,
            "engine": self.name, "engine_version": self.engine_version,
            "asset": to_dict(request.asset), "analysis_as_of": request.analysis_as_of,
            "status": top_status, "is_mock": False,
            "configuration": {
                "frequency": "1d", "feature_windows_bars": list(self.config.feature_windows),
                "realized_volatility_annualization_factor": annualization,
                "bollinger_stddevs": self.config.bollinger_stddevs,
                "volume_windows_bars": [self.config.volume_short_window, self.config.volume_long_window],
                "retrieval_warmup_calendar_years": self.config.retrieval_warmup_calendar_years,
                "primary_historical_context": {"years": self.config.primary_context_years, "role": "PRIMARY"},
                "secondary_historical_context": {"years": self.config.secondary_context_years, "role": "SECONDARY"},
                "percentile_convention": "inclusive average rank; raw low=0/high=1; compression=1-raw where defined",
            },
            "features": features,
            "data_quality": data_quality,
            "warnings": warnings,
            "provenance": [to_dict(dataset.provenance)],
        }

    @staticmethod
    def _rolling_realized_volatility(returns: list[float | None], window: int,
                                     annualization: int) -> list[float | None]:
        result: list[float | None] = [None] * len(returns)
        for i in range(window, len(returns)):
            values = returns[i - window + 1:i + 1]
            if all(value is not None for value in values):
                result[i] = pstdev(values) * sqrt(annualization)  # type: ignore[arg-type]
        return result

    @staticmethod
    def _rolling_normalized_atr(true_ranges: list[float], closes: list[float],
                                window: int) -> list[float | None]:
        result: list[float | None] = [None] * len(closes)
        for i in range(window - 1, len(closes)):
            result[i] = fmean(true_ranges[i - window + 1:i + 1]) / closes[i]
        return result

    @staticmethod
    def _rolling_bbw(closes: list[float], window: int, stddevs: float) -> list[float | None]:
        result: list[float | None] = [None] * len(closes)
        for i in range(window - 1, len(closes)):
            values = closes[i - window + 1:i + 1]
            middle = fmean(values)
            result[i] = (2 * stddevs * pstdev(values) / middle) if middle else None
        return result

    @staticmethod
    def _rolling_range(highs: list[float], lows: list[float], closes: list[float],
                       window: int) -> list[float | None]:
        result: list[float | None] = [None] * len(closes)
        for i in range(window - 1, len(closes)):
            result[i] = ((max(highs[i - window + 1:i + 1])
                          - min(lows[i - window + 1:i + 1])) / closes[i])
        return result

    @staticmethod
    def _rolling_volume_activity(volumes: list[float | None], short: int,
                                 long: int) -> list[float | None]:
        result: list[float | None] = [None] * len(volumes)
        for i in range(long - 1, len(volumes)):
            long_values = volumes[i - long + 1:i + 1]
            short_values = volumes[i - short + 1:i + 1]
            if any(value is None for value in long_values):
                continue
            long_avg = fmean(long_values)  # type: ignore[arg-type]
            result[i] = fmean(short_values) / long_avg if long_avg else None  # type: ignore[arg-type]
        return result

    def _feature_output(self, name: str, window: int, series: list[float | None],
                        dates: list[datetime], calendar_type: str, invert: bool,
                        parameters: dict[str, Any] | None = None,
                        unavailable: bool = False) -> dict[str, Any]:
        current = series[-1] if series else None
        status = "UNAVAILABLE" if unavailable else ("AVAILABLE" if current is not None else "INSUFFICIENT_DATA")
        contexts = {
            "5y": self._context(series, dates, len(series) - 1, self.config.primary_context_years,
                                "PRIMARY", calendar_type, invert),
            "3y": self._context(series, dates, len(series) - 1, self.config.secondary_context_years,
                                "SECONDARY", calendar_type, invert),
        }
        current_5 = contexts["5y"].get("compression_percentile")
        current_3 = contexts["3y"].get("compression_percentile")
        difference = (abs(current_5 - current_3)
                      if current_5 is not None and current_3 is not None else None)
        return {
            "feature_name": name, "window_bars": window, "parameters": parameters or {},
            "status": status, "current_raw_value": current,
            "raw_value_5_bars_ago": self._at(series, 5),
            "raw_value_20_bars_ago": self._at(series, 20),
            "raw_change_5_bars": self._difference(current, self._at(series, 5)),
            "raw_change_20_bars": self._difference(current, self._at(series, 20)),
            "historical_contexts": contexts,
            "absolute_3y_5y_compression_percentile_difference": difference,
        }

    def _context(self, series: list[float | None], dates: list[datetime], index: int,
                 years: int, role: str, calendar_type: str, invert: bool) -> dict[str, Any]:
        if index < 0 or index >= len(series) or series[index] is None:
            return self._empty_context(years, role, "UNAVAILABLE")
        evaluation_date = dates[index].date()
        start = _minus_years(evaluation_date, years)
        points = [(dates[i].date(), value) for i, value in enumerate(series[:index + 1])
                  if value is not None and start <= dates[i].date() <= evaluation_date]
        valid_dates = [dates[i].date() for i, value in enumerate(series[:index + 1]) if value is not None]
        tolerance = (self.config.context_start_tolerance_days_crypto
                     if calendar_type == TradingCalendarType.CONTINUOUS_24_7.value
                     else self.config.context_start_tolerance_days_equity)
        covered = bool(valid_dates) and valid_dates[0] <= start + timedelta(days=tolerance)
        expected = self._expected_observations(start, evaluation_date, calendar_type)
        density = len(points) / expected if expected else 0.0
        sufficient = covered and len(points) >= 2 and density >= self.config.context_min_density
        raw = percentile_rank([float(value) for _, value in points], float(series[index])) if sufficient else None
        compression = (1.0 - raw) if invert and raw is not None else None
        result = {
            "years": years, "role": role,
            "status": "AVAILABLE" if raw is not None else "INSUFFICIENT_DATA",
            "context_start_date": start.isoformat(), "context_end_date": evaluation_date.isoformat(),
            "observation_count": len(points), "observation_density": density,
            "raw_percentile": raw, "compression_percentile": compression,
            "compression_inversion_applied": invert,
        }
        for offset in (5, 20):
            prior = self._context_without_changes(series, dates, index - offset, years, calendar_type, invert)
            prior_value = prior.get("compression_percentile")
            result[f"compression_percentile_{offset}_bars_ago"] = prior_value
            result[f"compression_percentile_change_{offset}_bars"] = self._difference(compression, prior_value)
            result[f"raw_percentile_{offset}_bars_ago"] = prior.get("raw_percentile")
        return result

    def _context_without_changes(self, series, dates, index, years, calendar_type, invert):
        if index < 0 or index >= len(series) or series[index] is None:
            return {"raw_percentile": None, "compression_percentile": None}
        evaluation_date = dates[index].date()
        start = _minus_years(evaluation_date, years)
        points = [(dates[i].date(), value) for i, value in enumerate(series[:index + 1])
                  if value is not None and start <= dates[i].date() <= evaluation_date]
        valid_dates = [dates[i].date() for i, value in enumerate(series[:index + 1]) if value is not None]
        tolerance = (self.config.context_start_tolerance_days_crypto
                     if calendar_type == TradingCalendarType.CONTINUOUS_24_7.value
                     else self.config.context_start_tolerance_days_equity)
        expected = self._expected_observations(start, evaluation_date, calendar_type)
        sufficient = (bool(valid_dates) and valid_dates[0] <= start + timedelta(days=tolerance)
                      and len(points) >= 2 and bool(expected)
                      and len(points) / expected >= self.config.context_min_density)
        raw = percentile_rank([float(value) for _, value in points], float(series[index])) if sufficient else None
        return {"raw_percentile": raw,
                "compression_percentile": 1.0 - raw if invert and raw is not None else None}

    @staticmethod
    def _empty_context(years: int, role: str, status: str) -> dict[str, Any]:
        return {
            "years": years, "role": role, "status": status,
            "context_start_date": None, "context_end_date": None,
            "observation_count": 0, "observation_density": 0.0,
            "raw_percentile": None, "compression_percentile": None,
            "compression_inversion_applied": False,
            "compression_percentile_5_bars_ago": None,
            "compression_percentile_change_5_bars": None,
            "raw_percentile_5_bars_ago": None,
            "compression_percentile_20_bars_ago": None,
            "compression_percentile_change_20_bars": None,
            "raw_percentile_20_bars_ago": None,
        }

    @staticmethod
    def _at(series: list[float | None], offset: int) -> float | None:
        index = len(series) - 1 - offset
        return series[index] if index >= 0 else None

    @staticmethod
    def _difference(current: float | None, prior: float | None) -> float | None:
        return current - prior if current is not None and prior is not None else None

    @staticmethod
    def _expected_observations(start: date, end: date, calendar_type: str) -> int:
        days = (end - start).days + 1
        if calendar_type == TradingCalendarType.CONTINUOUS_24_7.value:
            return days
        return sum(1 for offset in range(days)
                   if (start + timedelta(days=offset)).weekday() < 5)

    @staticmethod
    def _has_insufficient_context(item: dict[str, Any]) -> bool:
        return any(context["status"] == "INSUFFICIENT_DATA"
                   for context in item["historical_contexts"].values())

    def _data_quality(self, dataset: Dataset, rows: list[dict[str, Any]],
                      calendar_type: str, warnings: list[str]) -> dict[str, Any]:
        metadata = dataset.metadata
        requested_start = metadata.requested_start_date if metadata else None
        requested_end = metadata.requested_end_date if metadata else None
        expected = None
        if requested_start and requested_end:
            expected = self._expected_observations(
                _dt(requested_start).date(), _dt(requested_end).date(), calendar_type
            )
        available = len(rows)
        volume_count = sum(row.get("volume") is not None for row in rows)
        volume_status = ("AVAILABLE" if volume_count == len(rows)
                         else "UNAVAILABLE" if volume_count == 0 else "PARTIAL")
        quality_status = "VALID" if volume_status == "AVAILABLE" else "PARTIAL"
        is_continuous = calendar_type == TradingCalendarType.CONTINUOUS_24_7.value
        weekday_gap_estimate = (
            max(expected - available, 0)
            if expected is not None and not is_continuous else None
        )
        return {
            "requested_observations": None,
            "requested_feature_warmup_bars": max(self.config.feature_windows),
            "estimated_expected_observations": expected,
            "available_observations": available,
            # Retained as a nullable compatibility field. Confirmed gaps require an
            # exchange/session calendar; weekday gaps include normal market holidays.
            "estimated_missing_observations": None,
            "confirmed_missing_sessions": None,
            "weekday_gap_estimate": weekday_gap_estimate,
            "missing_observations_note": (
                "confirmed_missing_sessions is unknown until exchange-calendar-aware "
                "validation exists; weekday_gap_estimate includes normal market holidays "
                "and is descriptive only"
                if not is_continuous else
                "confirmed_missing_sessions is unknown until session-aware validation exists"
            ),
            "volume_availability": volume_status,
            "adjustment_policy": (metadata.adjustment_policy if metadata
                                  else dataset.provenance.adjustment_policy),
            "trading_calendar_type": calendar_type,
            "requested_historical_start_date": requested_start,
            "requested_historical_end_date": requested_end,
            "actual_historical_start_date": metadata.actual_start_date if metadata else rows[0]["timestamp"],
            "actual_historical_end_date": metadata.actual_end_date if metadata else rows[-1]["timestamp"],
            "actual_observation_count": available,
            "quality_status": quality_status, "warnings": warnings,
        }
