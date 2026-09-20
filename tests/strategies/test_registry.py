import pytest

from tradingwaves.strategies.base import (
    UnknownStrategyError,
    available_strategies,
    get_strategy,
    register_strategy,
)


def test_registered_strategy_is_retrievable_by_name():
    @register_strategy("dummy_for_test")
    class Dummy:
        name = "dummy_for_test"

    assert get_strategy("dummy_for_test") is Dummy
    assert "dummy_for_test" in available_strategies()


def test_unknown_strategy_raises():
    with pytest.raises(UnknownStrategyError):
        get_strategy("no_such_strategy")


def test_duplicate_registration_raises():
    @register_strategy("dupe_for_test")
    class First:
        name = "dupe_for_test"

    with pytest.raises(ValueError):

        @register_strategy("dupe_for_test")
        class Second:
            name = "dupe_for_test"
