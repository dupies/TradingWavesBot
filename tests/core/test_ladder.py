import pytest

from tradingwaves.core.ladder import build_ladder
from tradingwaves.core.models import Direction, SymbolSpec

SPEC = SymbolSpec("EURUSD", 0.0001, 5, 0.01, 100.0, 0.01, 10.0)
PRICES = [1.1100, 1.1200, 1.1300, 1.1400]


def test_full_ladder_splits_evenly():
    ladder = build_ladder(0.40, PRICES, SPEC)

    assert len(ladder) == 4
    assert sum(tp.fraction for tp in ladder) == pytest.approx(1.0)
    assert [tp.index for tp in ladder] == [0, 1, 2, 3]


def test_small_lot_keeps_nearest_levels_and_drops_furthest():
    ladder = build_ladder(0.03, PRICES, SPEC)

    assert [tp.price for tp in ladder] == pytest.approx([1.1100, 1.1200, 1.1300])
    assert [tp.index for tp in ladder] == [0, 1, 2]
    assert sum(tp.fraction for tp in ladder) == pytest.approx(1.0)


def test_minimum_lot_collapses_to_single_target():
    ladder = build_ladder(0.01, PRICES, SPEC)

    assert len(ladder) == 1
    assert ladder[0].price == pytest.approx(1.1100)
    assert ladder[0].fraction == pytest.approx(1.0)


def test_sub_minimum_lot_yields_empty_ladder():
    assert build_ladder(0.004, PRICES, SPEC) == ()


def test_uneven_split_still_sums_to_whole_position():
    # 0.05 lots across 4 levels: 0.01 each with the remainder on the last
    ladder = build_ladder(0.05, PRICES, SPEC)

    assert sum(tp.fraction for tp in ladder) == pytest.approx(1.0)
    volumes = [round(tp.fraction * 0.05, 8) for tp in ladder]
    assert sum(volumes) == pytest.approx(0.05)
