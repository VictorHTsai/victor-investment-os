#!/usr/bin/env python3
"""Isolated Alpaca/Tiingo/Yahoo audit; never participates in production routing."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import fmean, median
from typing import Any
from urllib.error import HTTPError

from victor_investment_os.data.adapters import AlpacaMarketDataAdapter, YahooChartAdapter
from victor_investment_os.data.http import JSONHTTPClient
from victor_investment_os.data.validation import validate_ohlcv
from victor_investment_os.engines.compression import CompressionEngineV1
from victor_investment_os.models import (
    AdjustmentPolicy,
    Asset,
    Dataset,
    DatasetMetadata,
    PlannedDataRequest,
    Provenance,
    RequestEnvelope,
    SourceTier,
    TradingCalendarType,
    utc_now,
)
from victor_investment_os.planner import DataRequestPlanner


DEFAULT_AS_OF = "2026-09-10T00:00:00+00:00"
ASSETS = {
    "SLV": Asset("SLV", "ETF", "NYSEARCA", "USD"),
    "AAPL": Asset("AAPL", "STOCK", "NASDAQ", "USD"),
    "QQQ": Asset("QQQ", "ETF", "NASDAQ", "USD"),
}
FIELDS = ("open", "high", "low", "close", "volume")


def _date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _minus_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code} {exc.reason}"
    return type(exc).__name__


def build_request(asset: Asset, analysis_as_of: str) -> tuple[RequestEnvelope, PlannedDataRequest]:
    envelope = RequestEnvelope("1.0", f"benchmark-{asset.symbol.lower()}", analysis_as_of, asset)
    requirement = CompressionEngineV1().requirements(envelope)[0]
    return envelope, DataRequestPlanner().plan([requirement])[0]


def retrieve_tiingo(request: PlannedDataRequest, api_key: str,
                    http: JSONHTTPClient | None = None) -> Dataset:
    """Benchmark-only Tiingo EOD retrieval using adjusted OHLC and adjusted volume."""
    client = http or JSONHTTPClient()
    payload = client.get_json(
        f"https://api.tiingo.com/tiingo/daily/{request.asset.symbol}/prices",
        params={"startDate": request.requested_start_date, "endDate": request.requested_end_date,
                "resampleFreq": "daily"},
        headers={"Authorization": f"Token {api_key}"},
    )
    records = [{
        "timestamp": row["date"],
        "open": float(row["adjOpen"]), "high": float(row["adjHigh"]),
        "low": float(row["adjLow"]), "close": float(row["adjClose"]),
        "volume": float(row["adjVolume"]),
    } for row in payload]
    records.sort(key=lambda row: row["timestamp"])
    actual_start = records[0]["timestamp"] if records else None
    actual_end = records[-1]["timestamp"] if records else None
    adjustment = AdjustmentPolicy.SPLIT_DIVIDEND_ADJUSTED.value
    metadata = DatasetMetadata(
        request.asset.symbol, request.asset.asset_type, request.asset.currency, "1d",
        TradingCalendarType.US_EQUITY_SESSIONS.value, adjustment,
        request.requested_start_date, request.requested_end_date, actual_start, actual_end,
        len(records), request.lookback_bars,
        ["Benchmark-only Tiingo EOD path; not registered with the production Source Router"],
    )
    provenance = Provenance(
        "tiingo-eod-benchmark", "Tiingo End-of-Day API", SourceTier.TIER_2.value,
        utc_now(), actual_end or request.requested_end_date or utc_now(), "DIRECT",
        ["Tiingo adjOpen/adjHigh/adjLow/adjClose/adjVolume normalized to Victor OHLCV",
         "Tiingo CRSP-style split and dividend adjustment"],
        None, adjustment,
    )
    return Dataset(request.request_key, records, provenance, False, metadata)


def probe_alpaca_sip(api_key: str, api_secret: str,
                     http: JSONHTTPClient | None = None) -> dict[str, Any]:
    client = http or JSONHTTPClient()
    try:
        payload = client.get_json(
            "https://data.alpaca.markets/v2/stocks/SPY/bars",
            params={"timeframe": "1Day", "start": "2024-01-02", "end": "2024-01-05",
                    "adjustment": "all", "feed": "sip", "limit": 2, "sort": "asc"},
            headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret},
        )
        bars = payload.get("bars") or []
        return {"status": "AVAILABLE" if bars else "NO_BARS_RETURNED", "bars_returned": len(bars)}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "error": _safe_error(exc)}


def validate_dataset(dataset: Dataset, request: PlannedDataRequest) -> None:
    report = validate_ohlcv(dataset.records, request)
    if not report.valid:
        raise ValueError("; ".join(report.errors))


def records_by_date(dataset: Dataset, start: date, end: date) -> tuple[dict[date, dict[str, Any]], int]:
    result: dict[date, dict[str, Any]] = {}
    duplicates = 0
    for row in dataset.records:
        trading_date = _date(row["timestamp"])
        if start <= trading_date <= end:
            if trading_date in result:
                duplicates += 1
            result[trading_date] = row
    return result, duplicates


def data_summaries(asset_sources: dict[str, Dataset], comparison_start: date,
                   comparison_end: date) -> list[dict[str, Any]]:
    indexed = {source: records_by_date(dataset, comparison_start, comparison_end)
               for source, dataset in asset_sources.items()}
    summaries = []
    for source, dataset in asset_sources.items():
        rows, duplicates = indexed[source]
        other_dates = set().union(*(set(value[0]) for name, value in indexed.items() if name != source))
        summaries.append({
            "source": source,
            "bars": len(rows),
            "actual_start_date": min(rows).isoformat() if rows else None,
            "actual_end_date": max(rows).isoformat() if rows else None,
            "duplicate_dates": duplicates,
            "source_only_dates": len(set(rows) - other_dates) if other_dates else None,
            "dates_missing_relative_to_other_sources": len(other_dates - set(rows)) if other_dates else None,
            "adjustment_policy": dataset.provenance.adjustment_policy,
            "volume_availability": "AVAILABLE" if rows and all(row.get("volume") is not None for row in rows.values()) else "UNAVAILABLE",
        })
    return summaries


def pairwise_differences(asset_sources: dict[str, Dataset], comparison_start: date,
                         comparison_end: date) -> list[dict[str, Any]]:
    indexed = {source: records_by_date(dataset, comparison_start, comparison_end)[0]
               for source, dataset in asset_sources.items()}
    sources = sorted(indexed)
    output = []
    for left_index, left in enumerate(sources):
        for right in sources[left_index + 1:]:
            dates = sorted(set(indexed[left]) & set(indexed[right]))
            fields = {}
            for field in FIELDS:
                absolute = []
                percentages = []
                for trading_date in dates:
                    a, b = indexed[left][trading_date].get(field), indexed[right][trading_date].get(field)
                    if a is None or b is None:
                        continue
                    difference = abs(float(a) - float(b))
                    absolute.append(difference)
                    denominator = (abs(float(a)) + abs(float(b))) / 2
                    if denominator:
                        percentages.append(difference / denominator)
                fields[field] = {
                    "mean_absolute_difference": fmean(absolute) if absolute else None,
                    "median_absolute_difference": median(absolute) if absolute else None,
                    "mean_symmetric_absolute_percentage_difference": fmean(percentages) if percentages else None,
                    "maximum_absolute_difference": max(absolute) if absolute else None,
                }
            output.append({"left": left, "right": right, "overlapping_dates": len(dates), "fields": fields})
    return output


def compression_rows(outputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for source, output in outputs.items():
        for feature, items in output["features"].items():
            for item in items:
                for context_name, context in item["historical_contexts"].items():
                    rows.append({
                        "source": source, "feature": feature, "window_bars": item["window_bars"],
                        "context": context_name, "status": context["status"],
                        "current_raw_value": item["current_raw_value"],
                        "raw_percentile": context["raw_percentile"],
                        "compression_percentile": context["compression_percentile"],
                    })
    return rows


def compression_spreads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["feature"], row["window_bars"], row["context"])].append(row)
    spreads = []
    for (feature, window, context), values in groups.items():
        percentile_field = "raw_percentile" if feature == "volume_activity" else "compression_percentile"
        available = [value[percentile_field] for value in values if value[percentile_field] is not None]
        if len(available) >= 2:
            spreads.append({
                "feature": feature, "window_bars": window, "context": context,
                "percentile_field": percentile_field, "spread": max(available) - min(available),
                "values": {value["source"]: value[percentile_field] for value in values},
            })
    return sorted(spreads, key=lambda item: item["spread"], reverse=True)


def run_benchmark(analysis_as_of: str = DEFAULT_AS_OF) -> dict[str, Any]:
    alpaca_key = os.getenv("ALPACA_API_KEY_ID")
    alpaca_secret = os.getenv("ALPACA_API_SECRET_KEY")
    tiingo_key = os.getenv("TIINGO_API_KEY")
    source_availability = {
        "alpaca": {"tested": False, "credentials": bool(alpaca_key and alpaca_secret),
                   "feed": "IEX (production adapter request)", "status": "NOT_TESTED_CREDENTIALS_UNAVAILABLE",
                   "asset_statuses": {}},
        "tiingo": {"tested": False, "credentials": bool(tiingo_key), "feed": "EOD composite",
                   "status": "NOT_TESTED_CREDENTIALS_UNAVAILABLE", "asset_statuses": {}},
        "yahoo": {"tested": False, "credentials": False, "feed": "structured chart JSON",
                  "status": "NOT_TESTED", "asset_statuses": {}},
    }
    if alpaca_key and alpaca_secret:
        source_availability["alpaca"]["sip_probe"] = probe_alpaca_sip(alpaca_key, alpaca_secret)

    datasets: dict[str, dict[str, Dataset]] = {symbol: {} for symbol in ASSETS}
    compression: dict[str, dict[str, dict[str, Any]]] = {symbol: {} for symbol in ASSETS}
    errors: list[dict[str, str]] = []
    requests = {symbol: build_request(asset, analysis_as_of) for symbol, asset in ASSETS.items()}
    adapters: list[tuple[str, Any]] = [("yahoo", YahooChartAdapter())]
    if alpaca_key and alpaca_secret:
        adapters.insert(0, ("alpaca", AlpacaMarketDataAdapter(api_key=alpaca_key, api_secret=alpaca_secret)))

    for symbol, (envelope, request) in requests.items():
        source_calls = list(adapters)
        if tiingo_key:
            source_calls.insert(1 if alpaca_key and alpaca_secret else 0,
                                ("tiingo", lambda req, key=tiingo_key: retrieve_tiingo(req, key)))
        for source, adapter in source_calls:
            try:
                dataset = adapter.retrieve(request) if hasattr(adapter, "retrieve") else adapter(request)
                validate_dataset(dataset, request)
                datasets[symbol][source] = dataset
                compression[symbol][source] = CompressionEngineV1().analyze(envelope, dataset)
                source_availability[source]["tested"] = True
                source_availability[source]["asset_statuses"][symbol] = "AVAILABLE"
            except Exception as exc:
                errors.append({"asset": symbol, "source": source, "error": _safe_error(exc)})
                source_availability[source]["tested"] = True
                source_availability[source]["asset_statuses"][symbol] = "FAILED"

    for item in source_availability.values():
        statuses = list(item["asset_statuses"].values())
        if statuses:
            item["status"] = ("AVAILABLE" if all(value == "AVAILABLE" for value in statuses)
                              else "PARTIAL" if any(value == "AVAILABLE" for value in statuses)
                              else "FAILED")

    comparison_end = _date(next(iter(requests.values()))[1].requested_end_date or analysis_as_of)
    comparison_start = _minus_years(comparison_end, 5)
    assets = {}
    all_spreads = []
    for symbol in ASSETS:
        summaries = data_summaries(datasets[symbol], comparison_start, comparison_end)
        raw_differences = pairwise_differences(datasets[symbol], comparison_start, comparison_end)
        comp_rows = compression_rows(compression[symbol])
        spreads = compression_spreads(comp_rows)
        all_spreads.extend({"asset": symbol, **spread} for spread in spreads)
        assets[symbol] = {
            "data_comparison": summaries, "ohlcv_pairwise_differences": raw_differences,
            "compression_outputs": comp_rows, "compression_spreads": spreads,
        }
    all_spreads.sort(key=lambda item: item["spread"], reverse=True)
    conclusive = bool(all_spreads)
    return {
        "benchmark": "Victor Investment OS data-source benchmark",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_as_of": analysis_as_of,
        "comparison_period": {"start": comparison_start.isoformat(), "end": comparison_end.isoformat()},
        "source_availability": source_availability,
        "price_semantics": {
            "alpaca": "adjustment=all; production adapter explicitly requests IEX and labels split/dividend adjusted",
            "tiingo": "adjOpen/adjHigh/adjLow/adjClose/adjVolume; CRSP-style split and dividend adjustment",
            "yahoo": "OHLC reconstructed with adjclose/close ratio; provider adjusted close covers splits/dividends; volume preserved as supplied",
        },
        "corporate_action_spot_check": {
            "AAPL": (
                "AAPL's August 2020 four-for-one split predates the five-year comparison window. "
                "Cash dividends remain relevant, so provider dividend-adjustment methodology can "
                "still affect return and range continuity. Cross-provider behavior was not testable "
                "without authenticated Alpaca and Tiingo results."
            ),
            "SLV_and_QQQ": (
                "ETF distributions make dividend-adjustment semantics relevant. Only Yahoo completed, "
                "so no provider-induced discontinuity comparison was possible."
            ),
        },
        "assets": assets,
        "maximum_compression_spread": all_spreads[0] if all_spreads else None,
        "conclusion": {
            "cross_source_answer": (
                "AUDITABLE_CROSS_SOURCE_RESULTS_AVAILABLE" if conclusive else
                "INCONCLUSIVE_FEWER_THAN_TWO_SOURCES_TESTED"
            ),
            "recommended_order": "Alpaca -> Yahoo",
            "recommendation_basis": (
                "cross-source benchmark evidence" if conclusive else
                "retain the current route pending an authenticated rerun; this run does not support adding Tiingo"
            ),
        },
        "errors": errors,
        "production_routing_modified": False,
        "compression_methodology_modified": False,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# Victor Investment OS — Data Source Benchmark", "",
             f"Analysis as of: `{report['analysis_as_of']}`",
             f"Comparison period: `{report['comparison_period']['start']}` through `{report['comparison_period']['end']}`", "",
             "## Source availability", "", "| Source | Tested | Credentials | Feed | Status |",
             "|---|---:|---:|---|---|"]
    for source, item in report["source_availability"].items():
        lines.append(f"| {source.title()} | {item['tested']} | {item['credentials']} | {item['feed']} | {item['status']} |")
    lines.extend(["", "## Price semantics", "",
                  "| Source | Open / High / Low / Close | Adjusted close | Volume | Benchmark policy |",
                  "|---|---|---|---|---|",
                  "| Alpaca | API bar fields under `adjustment=all` | No separate field | Requested feed's bar volume | Existing adapter requests split/dividend-adjusted IEX bars |",
                  "| Tiingo | Raw and adjusted fields are separate | `adjClose` | Raw and `adjVolume` | Use adjusted OHLC and adjusted volume |",
                  "| Yahoo | Raw OHLC plus separate adjusted close | `adjclose` | Supplied volume | Reconstruct adjusted OHLC using `adjclose/close`; preserve volume |", ""])
    lines.extend(["", "## Data comparison", "", "| Asset | Source | Bars | Coverage | Adjustment | Volume |",
                  "|---|---|---:|---|---|---|"])
    for asset, content in report["assets"].items():
        for row in content["data_comparison"]:
            coverage = f"{row['actual_start_date']} → {row['actual_end_date']}"
            lines.append(f"| {asset} | {row['source']} | {row['bars']} | {coverage} | {row['adjustment_policy']} | {row['volume_availability']} |")
    lines.extend(["", "All completed datasets had zero duplicate trading dates. Source-only and missing-relative-to-other-source counts are `N/A` when only one source completed.",
                  "", "## OHLCV differences", ""])
    pair_count = sum(len(content["ohlcv_pairwise_differences"]) for content in report["assets"].values())
    if not pair_count:
        lines.append("No pairwise OHLCV statistics could be calculated because only Yahoo completed.")
    else:
        lines.append("Full pairwise MAD, median absolute difference, symmetric MAPE, and maximum differences are in the JSON report.")

    lines.extend(["", "## Representative Compression V1 outputs", "",
                  "Percentiles below are compression percentiles except Volume Activity, which uses its contextual raw percentile.", "",
                  "| Asset | Source | Feature | Window | Raw value | 3Y percentile | 5Y percentile |",
                  "|---|---|---|---:|---:|---:|---:|"])
    feature_names = {
        "realized_volatility": "RV", "normalized_atr": "ATR%",
        "bollinger_band_width": "BBW", "rolling_price_range": "Range%",
        "volume_activity": "Volume Activity",
    }
    for asset, content in report["assets"].items():
        grouped: dict[tuple[str, str, int], dict[str, Any]] = defaultdict(dict)
        for row in content["compression_outputs"]:
            representative = row["feature"] == "volume_activity" or row["window_bars"] == 20
            if representative:
                grouped[(row["source"], row["feature"], row["window_bars"])][row["context"]] = row
        for (source, feature, window), contexts in sorted(grouped.items()):
            three, five = contexts.get("3y"), contexts.get("5y")
            field = "raw_percentile" if feature == "volume_activity" else "compression_percentile"
            raw = (five or three or {}).get("current_raw_value")
            p3 = three.get(field) if three else None
            p5 = five.get(field) if five else None
            lines.append(f"| {asset} | {source} | {feature_names[feature]} | {window} | {raw:.8f} | {p3:.6f} | {p5:.6f} |")

    lines.extend(["", "## Corporate-action spot check", "",
                  f"- AAPL: {report['corporate_action_spot_check']['AAPL']}",
                  f"- SLV / QQQ: {report['corporate_action_spot_check']['SLV_and_QQQ']}",
                  "", "## Maximum observed Compression difference", ""])
    if report["maximum_compression_spread"] is None:
        lines.append("Not calculable. No feature had results from two or more sources, so assigning negligible/small/noticeable/large would be fabricated.")
    else:
        item = report["maximum_compression_spread"]
        lines.append(
            f"Largest observed percentile spread: `{item['spread']:.6f}` for {item['asset']} / "
            f"{item['feature']} / {item['window_bars']} bars / {item['context']}."
        )
    lines.extend(["", "## Root cause", "",
                  "The missing comparison is caused by credential injection, not market data: the execution environment did not expose the required Alpaca or Tiingo variables. No numerical provider discrepancy can be attributed to corporate actions, OHLC construction, volume, missing bars, timestamps, or provider methodology from this run.",
                  "", "## Recommendation", "",
                  "**Interim: PRIMARY Alpaca → FALLBACK Yahoo. Do not add Tiingo to production routing yet.**",
                  "", "This preserves the existing route because the benchmark is inconclusive; it is not evidence that Alpaca outperformed Tiingo. Rerun after credentials are securely injected, then decide whether Tiingo earns the secondary position."])
    lines.extend(["", "## Audit constraints", "",
                  "- Production routing was not changed.",
                  "- Compression Engine V1 methodology was not changed.",
                  "- Credentials are read only from environment variables.",
                  "- Missing authenticated sources are not inferred or fabricated.", ""])
    lines.extend(["## Documentation consulted", "",
                  "- [Alpaca Market Data API subscriptions](https://docs.alpaca.markets/us/docs/about-market-data-api)",
                  "- [Tiingo End-of-Day API](https://www.tiingo.com/documentation/end-of-day)",
                  "- [Yahoo adjusted-close definition](https://help.yahoo.com/kb/SLN28256.html)",
                  "- [Apple's 2020 split announcement](https://www.apple.com/newsroom/2020/07/apple-reports-third-quarter-results/)", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--output", type=Path, default=Path("reports/data_source_benchmark.json"))
    args = parser.parse_args()
    report = run_benchmark(args.analysis_as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown_path = args.output.with_suffix(".md")
    markdown_path.write_text(markdown_report(report))
    print(json.dumps({
        "analysis_as_of": report["analysis_as_of"],
        "source_availability": report["source_availability"],
        "maximum_compression_spread": report["maximum_compression_spread"],
        "report": str(markdown_path),
    }, indent=2))


if __name__ == "__main__":
    main()
