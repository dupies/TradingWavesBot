from datetime import UTC, datetime, timedelta

import pytest

from tradingwaves.core.metrics import compute_metrics
from tradingwaves.core.models import Fill, FillKind

NOW = datetime(2026, 9, 21, tzinfo=UTC)


def fill(profit: float, kind: FillKind = FillKind.TAKE_PROFIT, offset: int = 0) -> Fill:
    return Fill(1, NOW + timedelta(hours=offset), 1.1, 0.1, kind, profit)


def test_metrics_over_mixed_results():
    fills = [fill(100.0, offset=1), fill(-50.0, FillKind.STOP_LOSS, 2), fill(200.0, offset=3)]

    m = compute_metrics(fills, starting_equity=10_000.0)

    assert m.trades == 3
    assert m.wins == 2
    assert m.losses == 1
    assert m.net_profit == pytest.approx(250.0)
    assert m.profit_factor == pytest.approx(6.0)
    assert m.win_rate == pytest.approx(2 / 3)
    assert m.expectancy == pytest.approx(250.0 / 3)


def test_entry_fills_are_not_counted_as_trades():
    m = compute_metrics([fill(0.0, FillKind.ENTRY), fill(100.0, offset=1)], starting_equity=10_000.0)

    assert m.trades == 1


def test_no_fills_yields_zeroed_metrics():
    m = compute_metrics([], starting_equity=10_000.0)

    assert m.trades == 0
    assert m.profit_factor == 0.0
    assert m.max_drawdown == 0.0


def test_all_wins_gives_infinite_profit_factor():
    m = compute_metrics([fill(100.0), fill(50.0, offset=1)], starting_equity=10_000.0)

    assert m.profit_factor == float("inf")


def test_max_drawdown_measures_peak_to_trough():
    fills = [fill(500.0, offset=1), fill(-300.0, FillKind.STOP_LOSS, 2), fill(100.0, offset=3)]

    m = compute_metrics(fills, starting_equity=10_000.0)

    assert m.max_drawdown == pytest.approx(300.0)
