from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class JSONHTTPClient:
    """Tiny injectable HTTP boundary; unit tests supply deterministic fakes."""

    def get_json(self, url: str, *, params: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
        if params:
            url = f"{url}?{urlencode(params)}"
        request_headers = {"User-Agent": "VictorInvestmentOS/0.2 (+research prototype)"}
        request_headers.update(headers or {})
        request = Request(url, headers=request_headers)
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

