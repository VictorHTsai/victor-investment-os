from __future__ import annotations

import json

from .models import Asset, RequestEnvelope
from .orchestrator import build_phase1_orchestrator


def run_slv_example() -> dict:
    request = RequestEnvelope(
        contract_version="1.0", request_id="phase1-mock-slv-001",
        analysis_as_of="2026-09-09T00:00:00Z",
        asset=Asset("SLV", "ETF", "NYSEARCA", "USD"), mode="live",
    )
    return build_phase1_orchestrator().analyze(request)


def main() -> None:
    print(json.dumps(run_slv_example(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

