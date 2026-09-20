from datetime import UTC, datetime, timedelta

import pytest

from tradingwaves.brokers.sim_broker import SimBroker
from tradingwaves.core.models import Candle, Direction, FillKind, SymbolSpec, TakeProfit, Timeframe

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
START = datetime(2026, 9, 20, 8, tzinfo=UTC)


def candle(index: int, high: float, low: float, close: float, open_: float = 1.1000) -> Candle:
    return Candle("EURUSD", Timeframe.H1, START + timedelta(hours=index), open_, high, low, close, 100.0)


def test_advance_returns_candles_in_order():
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1005), candle(1, 1.1020, 1.1000, 1.1015)], SPEC)

    first = broker.advance()
    second = broker.advance()

    assert first.time < second.time
    assert broker.advance() is None


def test_take_profit_closes_only_its_fraction():
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1150, 1.1000, 1.1140)], SPEC)
    broker.advance()
    position = broker.open_position(
        "EURUSD",
        Direction.BUY,
        volume=0.40,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0), TakeProfit(1.1200, 0.25, 1)),
        magic=1,
    )

    broker.advance()

    assert position.remaining_volume == pytest.approx(0.30)
    assert position.filled_tp_indexes == [0]


def test_stop_loss_closes_whole_position():
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1010, 1.0940, 1.0945)], SPEC)
    broker.advance()
    broker.open_position(
        "EURUSD",
        Direction.BUY,
        volume=0.40,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0),),
        magic=1,
    )

    broker.advance()

    assert broker.open_positions() == []


def test_stop_is_evaluated_before_take_profit_within_one_candle():
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1150, 1.0940, 1.1000)], SPEC)
    broker.advance()
    broker.open_position(
        "EURUSD",
        Direction.BUY,
        volume=0.40,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0),),
        magic=1,
    )

    broker.advance()

    assert broker.open_positions() == []
    assert broker.fills[-1].kind is FillKind.STOP_LOSS


def test_sell_take_profit_triggers_on_low():
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1005, 1.0890, 1.0900)], SPEC)
    broker.advance()
    position = broker.open_position(
        "EURUSD",
        Direction.SELL,
        volume=0.40,
        stop_loss=1.1050,
        take_profits=(TakeProfit(1.0900, 0.25, 0),),
        magic=1,
    )

    broker.advance()

    assert position.filled_tp_indexes == [0]
    assert position.remaining_volume == pytest.approx(0.30)


def test_equity_reflects_realised_profit():
    broker = SimBroker(
        [candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1150, 1.1000, 1.1140)],
        SPEC,
        starting_equity=10_000.0,
        spread_pips=0.0,
    )
    broker.advance()
    broker.open_position(
        "EURUSD",
        Direction.BUY,
        volume=0.40,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0),),
        magic=1,
    )
    broker.advance()

    # Entry at candle-1 open 1.1000, TP at 1.1100 = 100 pips on 0.10 lots = $100
    assert broker.account_equity() == pytest.approx(10_100.0)


def test_modify_stop_updates_position():
    broker = SimBroker([candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1020, 1.1000, 1.1015)], SPEC)
    broker.advance()
    position = broker.open_position(
        "EURUSD", Direction.BUY, 0.10, 1.0950, (TakeProfit(1.1100, 1.0, 0),), magic=1
    )

    broker.modify_stop(position.ticket, 1.1000)

    assert broker.open_positions()[0].stop_loss == pytest.approx(1.1000)


def test_entry_price_includes_spread_for_buys():
    broker = SimBroker(
        [candle(0, 1.1010, 1.0990, 1.1000), candle(1, 1.1020, 1.1000, 1.1015, open_=1.1000)],
        SPEC,
        spread_pips=2.0,
    )
    broker.advance()
    position = broker.open_position(
        "EURUSD", Direction.BUY, 0.10, 1.0950, (TakeProfit(1.1100, 1.0, 0),), magic=1
    )

    # Fills at the next candle's open plus half the spread
    assert position.entry_price == pytest.approx(1.1001)
