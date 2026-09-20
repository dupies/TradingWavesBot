from datetime import UTC, datetime

from tradingwaves.core.models import (
    Candle,
    Direction,
    ModifyStop,
    Position,
    SymbolSpec,
    TakeProfit,
    Timeframe,
)
from tradingwaves.strategies.base import StrategyContext
from tradingwaves.strategies.range_1h import Range1H, Range1HConfig

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
NOW = datetime(2026, 9, 21, 10, tzinfo=UTC)


def position(filled: list[int], direction: Direction = Direction.BUY, stop: float = 1.0998) -> Position:
    return Position(
        ticket=1,
        symbol="EURUSD",
        direction=direction,
        volume=0.40,
        entry_price=1.1045,
        stop_loss=stop,
        take_profits=(TakeProfit(1.1145, 0.25, 0), TakeProfit(1.1245, 0.25, 1)),
        opened_at=NOW,
        magic=1,
        remaining_volume=0.40 - 0.10 * len(filled),
        filled_tp_indexes=list(filled),
    )


def bar() -> Candle:
    return Candle("EURUSD", Timeframe.H1, NOW, 1.1100, 1.1150, 1.1090, 1.1140, 100.0)


def ctx() -> StrategyContext:
    return StrategyContext(spec=SPEC, now=NOW, spread_pips=1.0, equity=10_000.0)


def test_no_action_before_first_take_profit():
    assert Range1H(Range1HConfig()).on_position_update(position([]), bar(), ctx()) == []


def test_stop_moves_to_breakeven_after_first_take_profit():
    strategy = Range1H(Range1HConfig(breakeven_after_tp1=True))

    assert strategy.on_position_update(position([0]), bar(), ctx()) == [ModifyStop(1.1045)]


def test_breakeven_move_is_not_repeated():
    strategy = Range1H(Range1HConfig(breakeven_after_tp1=True))

    assert strategy.on_position_update(position([0], stop=1.1045), bar(), ctx()) == []


def test_breakeven_disabled_does_nothing():
    strategy = Range1H(Range1HConfig(breakeven_after_tp1=False))

    assert strategy.on_position_update(position([0]), bar(), ctx()) == []


def test_short_position_moves_stop_down_to_breakeven():
    strategy = Range1H(Range1HConfig(breakeven_after_tp1=True))
    short = position([0], direction=Direction.SELL, stop=1.1100)

    assert strategy.on_position_update(short, bar(), ctx()) == [ModifyStop(1.1045)]


def test_short_position_with_stop_already_below_entry_does_nothing():
    strategy = Range1H(Range1HConfig(breakeven_after_tp1=True))
    short = position([0], direction=Direction.SELL, stop=1.1000)

    assert strategy.on_position_update(short, bar(), ctx()) == []
