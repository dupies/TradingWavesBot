from datetime import UTC, datetime

import pytest

from tradingwaves.core.models import Direction, RejectCode, Signal, SymbolSpec, TakeProfit
from tradingwaves.core.risk import AccountState, RiskEngine, RiskLimits


@pytest.fixture
def eurusd() -> SymbolSpec:
    return SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)


def make_signal(stop_loss: float, entry: float = 1.1000) -> Signal:
    return Signal(
        symbol="EURUSD",
        direction=Direction.BUY,
        stop_loss=stop_loss,
        take_profits=(TakeProfit(entry + 0.0100, 0.25, 0),),
        source="test",
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
        entry_price=entry,
    )


def test_sizes_position_from_percent_risk(eurusd):
    engine = RiskEngine(RiskLimits())
    account = AccountState(equity=10_000.0, balance=10_000.0, realized_pnl_today=0.0)

    decision = engine.evaluate(make_signal(1.0950), eurusd, account, [])

    assert decision.approved is True
    assert decision.lot == pytest.approx(0.20)


def test_rejects_when_lot_rounds_below_minimum(eurusd):
    engine = RiskEngine(RiskLimits())
    account = AccountState(equity=50.0, balance=50.0, realized_pnl_today=0.0)

    decision = engine.evaluate(make_signal(1.0000), eurusd, account, [])

    assert decision.approved is False
    assert decision.code is RejectCode.LOT_BELOW_MINIMUM


def test_rejects_when_daily_loss_cap_breached(eurusd):
    engine = RiskEngine(RiskLimits(daily_loss_cap_pct=3.0))
    account = AccountState(equity=9_700.0, balance=10_000.0, realized_pnl_today=-310.0)

    decision = engine.evaluate(make_signal(1.0950), eurusd, account, [])

    assert decision.approved is False
    assert decision.code is RejectCode.DAILY_LOSS_CAP


def test_allows_when_daily_loss_is_within_cap(eurusd):
    engine = RiskEngine(RiskLimits(daily_loss_cap_pct=3.0))
    account = AccountState(equity=9_900.0, balance=10_000.0, realized_pnl_today=-100.0)

    assert engine.evaluate(make_signal(1.0950), eurusd, account, []).approved is True


def test_rejects_when_max_positions_reached(eurusd):
    engine = RiskEngine(RiskLimits(max_concurrent_positions=1))
    account = AccountState(equity=10_000.0, balance=10_000.0, realized_pnl_today=0.0)

    decision = engine.evaluate(make_signal(1.0950), eurusd, account, [object()])

    assert decision.approved is False
    assert decision.code is RejectCode.MAX_POSITIONS


def test_rejects_signal_with_zero_stop_distance(eurusd):
    engine = RiskEngine(RiskLimits())
    account = AccountState(equity=10_000.0, balance=10_000.0, realized_pnl_today=0.0)

    decision = engine.evaluate(make_signal(1.1000), eurusd, account, [])

    assert decision.approved is False
    assert decision.code is RejectCode.INVALID_SIGNAL


def test_rejects_signal_with_stop_on_wrong_side(eurusd):
    engine = RiskEngine(RiskLimits())
    account = AccountState(equity=10_000.0, balance=10_000.0, realized_pnl_today=0.0)

    decision = engine.evaluate(make_signal(1.1050), eurusd, account, [])

    assert decision.approved is False
    assert decision.code is RejectCode.INVALID_SIGNAL


def test_rejects_when_total_risk_exceeds_exposure_limit(eurusd):
    from tradingwaves.core.models import Position

    engine = RiskEngine(RiskLimits(max_total_exposure_pct=2.0, max_concurrent_positions=10))
    account = AccountState(equity=10_000.0, balance=10_000.0, realized_pnl_today=0.0)
    # One open position already risking ~$150, new trade wants $100, cap is $200.
    existing = Position(
        ticket=1,
        symbol="EURUSD",
        direction=Direction.BUY,
        volume=0.30,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profits=(),
        opened_at=datetime(2026, 9, 20, tzinfo=UTC),
        magic=1,
        remaining_volume=0.30,
    )

    decision = engine.evaluate(make_signal(1.0950), eurusd, account, [existing])

    assert decision.approved is False
    assert decision.code is RejectCode.MAX_EXPOSURE


def test_position_with_stop_at_breakeven_contributes_no_risk(eurusd):
    from tradingwaves.core.models import Position

    engine = RiskEngine(RiskLimits(max_total_exposure_pct=2.0, max_concurrent_positions=10))
    account = AccountState(equity=10_000.0, balance=10_000.0, realized_pnl_today=0.0)
    breakeven = Position(
        ticket=1,
        symbol="EURUSD",
        direction=Direction.BUY,
        volume=0.30,
        entry_price=1.1000,
        stop_loss=1.1000,
        take_profits=(),
        opened_at=datetime(2026, 9, 20, tzinfo=UTC),
        magic=1,
        remaining_volume=0.30,
    )

    assert engine.evaluate(make_signal(1.0950), eurusd, account, [breakeven]).approved is True
