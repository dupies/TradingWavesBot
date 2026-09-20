#!/usr/bin/env python
"""Run a strategy over historical candles and print the results.

    python scripts/backtest.py --csv data/EURUSD_H1.csv --symbol EURUSD

Add --rejections to see why setups were skipped — usually more informative
than the win rate when a strategy trades less often than expected.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradingwaves.brokers.sim_broker import SimBroker  # noqa: E402
from tradingwaves.config import load_settings, load_symbol_specs  # noqa: E402
from tradingwaves.core.engine import Engine  # noqa: E402
from tradingwaves.core.journal import Journal  # noqa: E402
from tradingwaves.core.metrics import compute_metrics  # noqa: E402
from tradingwaves.core.models import Timeframe  # noqa: E402
from tradingwaves.core.risk import RiskEngine  # noqa: E402
from tradingwaves.data.csv_loader import load_candles_csv  # noqa: E402
from tradingwaves.strategies.base import get_strategy  # noqa: E402
from tradingwaves.strategies.range_1h import Range1HConfig  # noqa: E402

STRATEGY_CONFIGS = {"range_1h": Range1HConfig}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest a strategy over CSV candles")
    parser.add_argument("--csv", required=True, help="path to H1 candle CSV")
    parser.add_argument("--symbol", required=True, help="symbol name, e.g. EURUSD")
    parser.add_argument("--settings", default="config/settings.yaml")
    parser.add_argument("--symbols-file", default="config/symbols.yaml")
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--spread", type=float, default=1.0, help="simulated spread in pips")
    parser.add_argument("--rejections", action="store_true", help="list skipped setups")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    settings = load_settings(args.settings)
    specs = load_symbol_specs(args.symbols_file)
    if args.symbol not in specs:
        print(f"error: {args.symbol} is not defined in {args.symbols_file}", file=sys.stderr)
        return 2

    candles = load_candles_csv(args.csv, args.symbol, Timeframe.H1)
    if not candles:
        print(f"error: no candles loaded from {args.csv}", file=sys.stderr)
        return 2

    config_cls = STRATEGY_CONFIGS.get(settings.strategy)
    strategy_cls = get_strategy(settings.strategy)
    strategy = strategy_cls(config_cls(**settings.strategy_config) if config_cls else None)

    broker = SimBroker(candles, specs[args.symbol], args.equity, args.spread)
    engine = Engine(
        broker=broker,
        strategy=strategy,
        risk=RiskEngine(settings.risk),
        journal=Journal(":memory:"),
        magic=settings.magic,
    )

    while (candle := broker.advance()) is not None:
        engine.process_candle(candle)

    metrics = compute_metrics(broker.fills, args.equity)

    span = f"{candles[0].time:%Y-%m-%d} to {candles[-1].time:%Y-%m-%d}"
    print(f"\n{settings.strategy} on {args.symbol} — {len(candles)} candles, {span}\n")
    print(metrics.as_table())
    print(f"\nFinal equity   {broker.account_equity():>16,.2f}")
    if broker.open_positions():
        print(f"Still open     {len(broker.open_positions()):>16} position(s) at end of data")

    if args.rejections:
        rejections = engine.journal.rejections(limit=200)
        print(f"\nSkipped setups ({len(rejections)}):")
        for row in rejections:
            print(f"  {row['code']:<20} {row['reason']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
