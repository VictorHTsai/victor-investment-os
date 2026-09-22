from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("apps/dge-dashboard/data/cycle-latest.json")
TARGET_HALVING_HEIGHT = 1_050_000
WINDOW_DAYS = 30
MEMPOOL = "https://mempool.space/api"

def get_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Victor-Investment-OS/1.0"})
    with urlopen(req, timeout=20) as r:
        return r.read().decode().strip()

def get_json(url: str):
    req = Request(url, headers={"User-Agent": "Victor-Investment-OS/1.0"})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def cycle_status(now, buy_start, buy_end, sell_start, sell_end):
    if now < buy_start: return "PREPARE FOR ACCUMULATION"
    if now <= buy_end: return "ACCUMULATION WINDOW"
    if now < sell_start: return "POST-ACCUMULATION"
    if now <= sell_end: return "DISTRIBUTION WATCH"
    return "MONITOR"

def main():
    now = datetime.now(timezone.utc)
    tip_height = int(get_text(f"{MEMPOOL}/blocks/tip/height"))
    tip_hash = get_text(f"{MEMPOOL}/block-height/{tip_height}")
    tip = get_json(f"{MEMPOOL}/block/{tip_hash}")
    tip_time = datetime.fromtimestamp(tip["timestamp"], timezone.utc)

    remaining = TARGET_HALVING_HEIGHT - tip_height
    if remaining <= 0:
        raise RuntimeError("Target halving height already reached; advance target height")

    # Halving is defined by block height, not a fixed calendar date.
    # Project remaining blocks at Bitcoin's 10-minute target cadence.
    halving = tip_time + timedelta(minutes=remaining * 10)
    buy = halving - timedelta(days=500)
    sell = halving + timedelta(days=500)
    buy_start, buy_end = buy - timedelta(days=WINDOW_DAYS), buy + timedelta(days=WINDOW_DAYS)
    sell_start, sell_end = sell - timedelta(days=WINDOW_DAYS), sell + timedelta(days=WINDOW_DAYS)

    out = {
        "schema_version": "btc-cycle-strategic-v1",
        "as_of": now.isoformat(),
        "methodology": "BLOCK_HEIGHT_TARGET_CADENCE_500D",
        "source": "mempool.space public API",
        "target_halving_height": TARGET_HALVING_HEIGHT,
        "current_block_height": tip_height,
        "projection_minutes_per_block": 10.0,
        "estimated_halving": halving.date().isoformat(),
        "exact_buy_date": buy.date().isoformat(),
        "buy_window_start": buy_start.date().isoformat(),
        "buy_window_end": buy_end.date().isoformat(),
        "exact_sell_date": sell.date().isoformat(),
        "sell_window_start": sell_start.date().isoformat(),
        "sell_window_end": sell_end.date().isoformat(),
        "days_to_buy_window": (buy_start.date() - now.date()).days,
        "signal": cycle_status(now, buy_start, buy_end, sell_start, sell_end),
        "window_days": WINDOW_DAYS,
        "note": "Calendar halving date is an estimate; it updates as block height advances."
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out))

if __name__ == "__main__":
    main()
