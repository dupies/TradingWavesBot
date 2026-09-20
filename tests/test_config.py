import pytest

from tradingwaves.config import load_settings, load_symbol_specs

SETTINGS = """
broker: sim
magic: 770001
strategy: range_1h
symbols: [EURUSD, GBPUSD]
risk:
  risk_per_trade_pct: 1.0
  daily_loss_cap_pct: 3.0
  max_concurrent_positions: 3
  max_total_exposure_pct: 10.0
strategy_config:
  session_hour: 8
  session_timezone: Europe/London
""".strip()

SYMBOLS = """
EURUSD:
  pip_size: 0.0001
  digits: 5
  min_lot: 0.01
  max_lot: 100.0
  lot_step: 0.01
  pip_value_per_lot: 10.0
""".strip()


def test_loads_settings(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(SETTINGS)

    settings = load_settings(path)

    assert settings.broker == "sim"
    assert settings.symbols == ["EURUSD", "GBPUSD"]
    assert settings.risk.risk_per_trade_pct == 1.0
    assert settings.strategy_config["session_hour"] == 8


def test_loads_symbol_specs(tmp_path):
    path = tmp_path / "symbols.yaml"
    path.write_text(SYMBOLS)

    specs = load_symbol_specs(path)

    assert specs["EURUSD"].pip_size == 0.0001
    assert specs["EURUSD"].pips_to_price(10) == pytest.approx(0.001)


def test_shipped_config_files_are_valid():
    settings = load_settings("config/settings.yaml")
    specs = load_symbol_specs("config/symbols.yaml")

    assert settings.strategy == "range_1h"
    for symbol in settings.symbols:
        assert symbol in specs


def test_unknown_risk_key_is_rejected(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(SETTINGS.replace("risk_per_trade_pct: 1.0", "risk_per_trade_pcnt: 1.0"))

    with pytest.raises(ValueError, match="risk_per_trade_pcnt"):
        load_settings(path)
