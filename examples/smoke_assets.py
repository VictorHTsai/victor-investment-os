from __future__ import annotations

import json

from victor_investment_os.real_example import ASSETS, analyze_real_asset


def main() -> None:
    summaries = []
    for symbol in ASSETS:
        result = analyze_real_asset(symbol)
        summaries.append({
            "symbol": symbol, "status": result.get("status"),
            "provider": (result.get("provenance") or [{}])[0].get("source_name"),
            "observations": result.get("data_quality", {}).get("actual_observation_count"),
            "adjustment_policy": result.get("data_quality", {}).get("adjustment_policy"),
            "warnings": result.get("warnings", []), "failures": result.get("failures", []),
        })
    print(json.dumps(summaries, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

