from datetime import UTC, datetime, timedelta

from tradingwaves.core.models import Candle, RejectCode, SymbolSpec, Timeframe
from tradingwaves.strategies.base import StrategyContext
from tradingwaves.strategies.range_1h import Range1H, Range1HConfig

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
SESSION_UTC = datetime(2026, 9, 21, 7, tzinfo=UTC)


def candle(hours: int, high: float, low: float, close: float) -> Candle:
    return Candle(
        "EURUSD", Timeframe.H1, SESSION_UTC + timedelta(hours=hours), 1.1000, high, low, close, 100.0
    )


def ctx(t: datetime, spread: float = 1.0) -> StrategyContext:
    return StrategyContext(spec=SPEC, now=t, spread_pips=spread, equity=10_000.0)


def test_range_below_minimum_is_rejected():
    strategy = Range1H(Range1HConfig(min_range_pips=5.0))

    strategy.on_candle(candle(0, 1.1003, 1.1000, 1.1002), ctx(SESSION_UTC))
    signal = strategy.on_candle(candle(1, 1.1010, 1.1004, 1.1008), ctx(SESSION_UTC + timedelta(hours=1)))

    assert signal is None
    assert strategy.last_reject[0] is RejectCode.RANGE_TOO_SMALL


def test_range_above_maximum_is_rejected():
    strategy = Range1H(Range1HConfig(max_range_pips=60.0))

    strategy.on_candle(candle(0, 1.1100, 1.1000, 1.1050), ctx(SESSION_UTC))
    signal = strategy.on_candle(candle(1, 1.1150, 1.1090, 1.1140), ctx(SESSION_UTC + timedelta(hours=1)))

    assert signal is None
    assert strategy.last_reject[0] is RejectCode.RANGE_TOO_WIDE


def test_wide_spread_is_rejected():
    strategy = Range1H(Range1HConfig(max_spread_pips=3.0))

    strategy.on_candle(candle(0, 1.1030, 1.1000, 1.1020), ctx(SESSION_UTC))
    signal = strategy.on_candle(
        candle(1, 1.1050, 1.1025, 1.1045), ctx(SESSION_UTC + timedelta(hours=1), spread=9.0)
    )

    assert signal is None
    assert strategy.last_reject[0] is RejectCode.SPREAD_TOO_WIDE


def test_rejected_setup_does_not_retry_later_in_the_day():
    strategy = Range1H(Range1HConfig(min_range_pips=5.0))

    strategy.on_candle(candle(0, 1.1003, 1.1000, 1.1002), ctx(SESSION_UTC))
    strategy.on_candle(candle(1, 1.1010, 1.1004, 1.1008), ctx(SESSION_UTC + timedelta(hours=1)))
    later = strategy.on_candle(candle(2, 1.1060, 1.1030, 1.1055), ctx(SESSION_UTC + timedelta(hours=2)))

    assert later is None


def test_clean_setup_leaves_no_rejection():
    strategy = Range1H(Range1HConfig())

    strategy.on_candle(candle(0, 1.1030, 1.1000, 1.1020), ctx(SESSION_UTC))
    signal = strategy.on_candle(candle(1, 1.1050, 1.1025, 1.1045), ctx(SESSION_UTC + timedelta(hours=1)))

    assert signal is not None
    assert strategy.last_reject is None
