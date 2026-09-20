from datetime import UTC, datetime, timedelta

import pytest

from tradingwaves.core.models import Candle, Direction, SymbolSpec, Timeframe
from tradingwaves.strategies.base import StrategyContext
from tradingwaves.strategies.range_1h import Range1H, Range1HConfig

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
# 08:00 Europe/London in September is 07:00 UTC (BST = UTC+1).
SESSION_UTC = datetime(2026, 9, 21, 7, tzinfo=UTC)


def candle(hours: int, high: float, low: float, close: float) -> Candle:
    return Candle(
        "EURUSD", Timeframe.H1, SESSION_UTC + timedelta(hours=hours), 1.1000, high, low, close, 100.0
    )


def ctx(t: datetime, spread: float = 1.0) -> StrategyContext:
    return StrategyContext(spec=SPEC, now=t, spread_pips=spread, equity=10_000.0)


def feed(strategy: Range1H, candles: list[Candle]):
    return [strategy.on_candle(c, ctx(c.time)) for c in candles]


def test_range_candle_alone_emits_no_signal():
    strategy = Range1H(Range1HConfig())

    assert strategy.on_candle(candle(0, 1.1030, 1.1000, 1.1020), ctx(SESSION_UTC)) is None


def test_candles_before_the_session_hour_are_ignored():
    strategy = Range1H(Range1HConfig())
    pre_session = Candle(
        "EURUSD", Timeframe.H1, SESSION_UTC - timedelta(hours=2), 1.1000, 1.1030, 1.1000, 1.1025, 100.0
    )

    assert strategy.on_candle(pre_session, ctx(pre_session.time)) is None


def test_close_above_range_high_emits_buy_with_range_low_stop():
    strategy = Range1H(Range1HConfig(sl_buffer_pips=2.0))

    signals = feed(strategy, [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)])

    signal = signals[1]
    assert signal is not None
    assert signal.direction is Direction.BUY
    assert signal.stop_loss == pytest.approx(1.0998)
    assert len(signal.take_profits) == 4


def test_close_below_range_low_emits_sell_with_range_high_stop():
    strategy = Range1H(Range1HConfig(sl_buffer_pips=2.0))

    signals = feed(strategy, [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1025, 1.0980, 1.0990)])

    signal = signals[1]
    assert signal is not None
    assert signal.direction is Direction.SELL
    assert signal.stop_loss == pytest.approx(1.1032)


def test_close_inside_range_waits_then_abandons_after_window():
    strategy = Range1H(Range1HConfig(confirmation_window=2))

    signals = feed(
        strategy,
        [
            candle(0, 1.1030, 1.1000, 1.1020),
            candle(1, 1.1028, 1.1005, 1.1010),
            candle(2, 1.1029, 1.1002, 1.1015),
            candle(3, 1.1060, 1.1030, 1.1055),
        ],
    )

    assert signals[1] is None
    assert signals[2] is None
    assert signals[3] is None


def test_breakout_within_window_still_trades():
    strategy = Range1H(Range1HConfig(confirmation_window=3))

    signals = feed(
        strategy,
        [
            candle(0, 1.1030, 1.1000, 1.1020),
            candle(1, 1.1028, 1.1005, 1.1010),
            candle(2, 1.1060, 1.1030, 1.1055),
        ],
    )

    assert signals[1] is None
    assert signals[2] is not None


def test_only_one_trade_per_day():
    strategy = Range1H(Range1HConfig())

    signals = feed(
        strategy,
        [
            candle(0, 1.1030, 1.1000, 1.1020),
            candle(1, 1.1050, 1.1025, 1.1045),
            candle(2, 1.1070, 1.1045, 1.1065),
        ],
    )

    assert signals[1] is not None
    assert signals[2] is None


def test_new_session_day_resets_the_setup():
    strategy = Range1H(Range1HConfig())

    feed(strategy, [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)])
    next_day = feed(strategy, [candle(24, 1.1230, 1.1200, 1.1220), candle(25, 1.1250, 1.1225, 1.1245)])

    assert next_day[1] is not None


def test_take_profit_ladder_uses_configured_pip_distances():
    strategy = Range1H(Range1HConfig(tp_pips=(100.0, 200.0, 300.0, 400.0)))

    signals = feed(strategy, [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)])

    tps = signals[1].take_profits
    assert [tp.price for tp in tps] == pytest.approx([1.1145, 1.1245, 1.1345, 1.1445])
    assert [tp.fraction for tp in tps] == pytest.approx([0.25, 0.25, 0.25, 0.25])


def test_sell_ladder_runs_downwards():
    strategy = Range1H(Range1HConfig(tp_pips=(100.0, 200.0)))

    signals = feed(strategy, [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1025, 1.0980, 1.0990)])

    tps = signals[1].take_profits
    assert [tp.price for tp in tps] == pytest.approx([1.0890, 1.0790])
