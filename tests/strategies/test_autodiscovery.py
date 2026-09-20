def test_shipped_strategies_register_on_package_import():
    # Importing the package alone must be enough — no explicit module import.
    import tradingwaves.strategies  # noqa: F401
    from tradingwaves.strategies.base import available_strategies, get_strategy

    assert "range_1h" in available_strategies()
    assert get_strategy("range_1h").name == "range_1h"
