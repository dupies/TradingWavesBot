from datetime import UTC, datetime, timedelta

import pytest

from tradingwaves.brokers.sim_broker import SimBroker
from tradingwaves.core.engine import Engine
from tradingwaves.core.journal import Journal
from tradingwaves.core.models import (
    Candle,
    Direction,
    Signal,
    SymbolSpec,
    TakeProfit,
    Timeframe,
)
from tradingwaves.core.risk import RiskEngine, RiskLimits
from tradingwaves.strategies.range_1h import Range1H, Range1HConfig

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
SESSION_UTC = datetime(2026, 9, 21, 7, tzinfo=UTC)
MAGIC = 770001


def candle(hours: int, high: float, low: float, close: float, open_: float = 1.1000) -> Candle:
    return Candle(
        "EURUSD", Timeframe.H1, SESSION_UTC + timedelta(hours=hours), open_, high, low, close, 100.0
    )


def build(candles, config: Range1HConfig | None = None, limits: RiskLimits | None = None):
    broker = SimBroker(candles, SPEC, starting_equity=10_000.0)
    engine = Engine(
        broker=broker,
        strategy=Range1H(config or Range1HConfig()),
        risk=RiskEngine(limits or RiskLimits()),
        journal=Journal(":memory:"),
        magic=MAGIC,
    )
    return broker, engine


def run(broker: SimBroker, engine: Engine) -> None:
    while (c := broker.advance()) is not None:
        engine.process_candle(c)


def test_breakout_opens_a_sized_position():
    broker, engine = build([candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)])

    run(broker, engine)

    positions = broker.open_positions()
    assert len(positions) == 1
    assert positions[0].direction is Direction.BUY
    assert positions[0].volume > 0
    assert positions[0].magic == MAGIC


def test_opened_position_is_journalled():
    broker, engine = build([candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)])

    run(broker, engine)

    ticket = broker.open_positions()[0].ticket
    assert engine.journal.position_by_ticket(ticket) is not None


def test_rejected_signal_is_journalled_and_opens_nothing():
    broker, engine = build([candle(0, 1.1003, 1.1000, 1.1002), candle(1, 1.1012, 1.1004, 1.1010)])

    run(broker, engine)

    assert broker.open_positions() == []
    assert len(engine.journal.rejections()) >= 1


def test_risk_rejection_is_journalled():
    # Cap already breached, so the risk engine must veto a valid setup.
    broker, engine = build(
        [candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)],
        limits=RiskLimits(max_concurrent_positions=0),
    )

    run(broker, engine)

    assert broker.open_positions() == []
    codes = [r["code"] for r in engine.journal.rejections()]
    assert "MAX_POSITIONS" in codes


def test_take_profit_moves_stop_to_breakeven():
    broker, engine = build(
        [
            candle(0, 1.1030, 1.1000, 1.1020),
            candle(1, 1.1050, 1.1025, 1.1045),
            candle(2, 1.1160, 1.1040, 1.1150),  # touches TP1 at 1.1145
            candle(3, 1.1170, 1.1100, 1.1160),
        ]
    )

    run(broker, engine)

    position = broker.open_positions()[0]
    assert position.filled_tp_indexes == [0]
    assert position.stop_loss == pytest.approx(position.entry_price)


def test_reconcile_ignores_positions_not_in_journal():
    broker, engine = build([candle(0, 1.1030, 1.1000, 1.1020)])
    broker.advance()
    broker.open_position(
        "EURUSD",
        Direction.BUY,
        volume=0.10,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 1.0, 0),),
        magic=999999,
    )

    adopted = engine.reconcile()

    assert adopted == []
    assert len(broker.open_positions()) == 1


def test_reconcile_adopts_journalled_position():
    broker, engine = build([candle(0, 1.1030, 1.1000, 1.1020), candle(1, 1.1050, 1.1025, 1.1045)])
    run(broker, engine)
    ticket = broker.open_positions()[0].ticket

    engine.positions.clear()  # simulate a restart losing in-memory state
    adopted = engine.reconcile()

    assert [p.ticket for p in adopted] == [ticket]
    assert ticket in {p.ticket for p in engine.positions}


def test_stop_loss_fill_is_journalled_and_counted_against_the_daily_cap():
    broker, engine = build(
        [
            candle(0, 1.1030, 1.1000, 1.1020),
            candle(1, 1.1050, 1.1025, 1.1045),
            candle(2, 1.1050, 1.0980, 1.0990),  # takes out the stop at 1.0998
        ]
    )

    run(broker, engine)

    assert broker.open_positions() == []
    assert engine.realized_pnl_today < 0
    kinds = [f["kind"] for f in engine.journal.fills_for_ticket(1)]
    assert "STOP_LOSS" in kinds


def test_daily_loss_cap_blocks_a_later_setup():
    # A losing trade on day one, then a fresh setup the same day must be vetoed
    # once the cap is breached.
    engine_limits = RiskLimits(daily_loss_cap_pct=0.1, max_concurrent_positions=5)
    broker, engine = build(
        [
            candle(0, 1.1030, 1.1000, 1.1020),
            candle(1, 1.1050, 1.1025, 1.1045),
            # Opens at the prior close, as a real candle does, so the fill price
            # matches the price the position was sized against.
            candle(2, 1.1050, 1.0980, 1.0990, open_=1.1045),
        ],
        limits=engine_limits,
    )
    run(broker, engine)
    assert engine.realized_pnl_today < 0

    later = Signal(
        symbol="EURUSD",
        direction=Direction.BUY,
        stop_loss=1.0900,
        take_profits=(TakeProfit(1.1100, 1.0, 0),),
        source="manual",
        created_at=SESSION_UTC + timedelta(hours=4),
        entry_price=1.1000,
    )

    assert engine.submit(later) is None
    assert "DAILY_LOSS_CAP" in [r["code"] for r in engine.journal.rejections()]


def test_new_day_resets_the_daily_loss_tally():
    broker, engine = build(
        [
            candle(0, 1.1030, 1.1000, 1.1020),
            candle(1, 1.1050, 1.1025, 1.1045),
            candle(2, 1.1050, 1.0980, 1.0990),
            candle(24, 1.1230, 1.1200, 1.1220),
        ]
    )

    run(broker, engine)

    assert engine.realized_pnl_today == 0.0
