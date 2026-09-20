from datetime import UTC, datetime

from tradingwaves.core.journal import Journal
from tradingwaves.core.models import (
    Direction,
    Fill,
    FillKind,
    Position,
    RejectCode,
    Signal,
    TakeProfit,
)
from tradingwaves.core.risk import RiskDecision

NOW = datetime(2026, 9, 20, 8, tzinfo=UTC)


def make_signal() -> Signal:
    return Signal(
        symbol="EURUSD",
        direction=Direction.BUY,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0),),
        source="range_1h",
        created_at=NOW,
        entry_price=1.1000,
    )


def make_position(ticket: int = 501) -> Position:
    return Position(
        ticket=ticket,
        symbol="EURUSD",
        direction=Direction.BUY,
        volume=0.20,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profits=(TakeProfit(1.1100, 0.25, 0),),
        opened_at=NOW,
        magic=770001,
        remaining_volume=0.20,
    )


def test_records_signal_and_returns_id():
    journal = Journal(":memory:")

    signal_id = journal.record_signal(make_signal())

    assert isinstance(signal_id, int)
    assert signal_id > 0


def test_rejection_is_retrievable_with_reason_code():
    journal = Journal(":memory:")
    signal_id = journal.record_signal(make_signal())

    journal.record_decision(
        signal_id,
        RiskDecision(False, 0.0, "range 3.0 pips below minimum", RejectCode.RANGE_TOO_SMALL),
    )

    rejections = journal.rejections()
    assert len(rejections) == 1
    assert rejections[0]["code"] == RejectCode.RANGE_TOO_SMALL.value
    assert "below minimum" in rejections[0]["reason"]


def test_approved_decision_is_not_listed_as_rejection():
    journal = Journal(":memory:")
    signal_id = journal.record_signal(make_signal())

    journal.record_decision(signal_id, RiskDecision(True, 0.20, "sized ok"))

    assert journal.rejections() == []


def test_position_is_retrievable_by_ticket():
    journal = Journal(":memory:")
    signal_id = journal.record_signal(make_signal())

    journal.record_position(signal_id, make_position(ticket=501))

    row = journal.position_by_ticket(501)
    assert row is not None
    assert row["symbol"] == "EURUSD"
    assert row["magic"] == 770001


def test_unknown_ticket_returns_none():
    assert Journal(":memory:").position_by_ticket(999) is None


def test_fills_are_recorded_against_their_ticket():
    journal = Journal(":memory:")
    signal_id = journal.record_signal(make_signal())
    journal.record_position(signal_id, make_position(ticket=501))

    journal.record_fill(Fill(501, NOW, 1.1100, 0.05, FillKind.TAKE_PROFIT, 50.0))

    fills = journal.fills_for_ticket(501)
    assert len(fills) == 1
    assert fills[0]["kind"] == FillKind.TAKE_PROFIT.value
    assert fills[0]["profit"] == 50.0
