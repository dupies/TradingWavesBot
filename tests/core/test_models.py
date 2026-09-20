import pytest

from tradingwaves.core.models import SymbolSpec


@pytest.fixture
def eurusd() -> SymbolSpec:
    return SymbolSpec(
        symbol="EURUSD",
        pip_size=0.0001,
        digits=5,
        min_lot=0.01,
        max_lot=100.0,
        lot_step=0.01,
        pip_value_per_lot=10.0,
    )


def test_pips_to_price(eurusd):
    assert eurusd.pips_to_price(100) == pytest.approx(0.0100)


def test_price_to_pips(eurusd):
    assert eurusd.price_to_pips(0.0035) == pytest.approx(35.0)


def test_round_lot_rounds_down_to_step(eurusd):
    assert eurusd.round_lot(0.1789) == pytest.approx(0.17)


def test_round_lot_below_minimum_returns_zero(eurusd):
    assert eurusd.round_lot(0.004) == 0.0


def test_round_lot_clamps_to_maximum(eurusd):
    assert eurusd.round_lot(250.0) == pytest.approx(100.0)
