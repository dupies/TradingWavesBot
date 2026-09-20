"""YAML configuration loading.

Unknown keys are an error rather than a silent default: a typo in a risk
limit should stop the bot, not quietly halve the protection it was meant to
provide.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml

from tradingwaves.core.models import SymbolSpec
from tradingwaves.core.risk import RiskLimits


@dataclass(frozen=True)
class Settings:
    broker: str
    magic: int
    symbols: list[str]
    strategy: str
    risk: RiskLimits
    strategy_config: dict


def _strict(cls, data: dict, where: str):
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"unknown {where} setting(s): {', '.join(sorted(unknown))}")
    return cls(**data)


def load_settings(path: str | Path) -> Settings:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    risk = _strict(RiskLimits, raw.get("risk", {}) or {}, "risk")
    return Settings(
        broker=raw.get("broker", "sim"),
        magic=int(raw.get("magic", 770001)),
        symbols=list(raw.get("symbols", [])),
        strategy=raw.get("strategy", "range_1h"),
        risk=risk,
        strategy_config=raw.get("strategy_config", {}) or {},
    )


def load_symbol_specs(path: str | Path) -> dict[str, SymbolSpec]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    specs: dict[str, SymbolSpec] = {}
    for symbol, values in raw.items():
        specs[symbol] = SymbolSpec(symbol=symbol, **values)
    return specs
