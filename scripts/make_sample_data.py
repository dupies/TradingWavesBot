#!/usr/bin/env python
"""Generate synthetic H1 candles so the pipeline can be exercised end to end.

This is a random walk. It is NOT market data and says nothing whatsoever
about whether the strategy is profitable — it exists only to prove the
plumbing works before real history is available.

    python scripts/make_sample_data.py --out data/EURUSD_H1_synthetic.csv
"""

from __future__ import annotations

import argparse
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/EURUSD_H1_synthetic.csv")
    parser.add_argument("--weeks", type=int, default=26)
    parser.add_argument("--start-price", type=float, default=1.1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    time = datetime(2025, 1, 6, 0, tzinfo=UTC)  # a Monday
    price = args.start_price
    rows = ["time,open,high,low,close,volume"]

    for _ in range(args.weeks * 5 * 24):
        if time.weekday() >= 5:  # skip the weekend
            time += timedelta(hours=1)
            continue
        drift = random.gauss(0, 0.0012)
        open_ = price
        close = round(open_ + drift, 5)
        high = round(max(open_, close) + abs(random.gauss(0, 0.0004)), 5)
        low = round(min(open_, close) - abs(random.gauss(0, 0.0004)), 5)
        rows.append(
            f"{time:%Y-%m-%dT%H:%M:%S},{open_:.5f},{high:.5f},{low:.5f},{close:.5f},{random.randint(50, 500)}"
        )
        price = close
        time += timedelta(hours=1)

    out.write_text("\n".join(rows) + "\n")
    print(f"wrote {len(rows) - 1} synthetic candles to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
