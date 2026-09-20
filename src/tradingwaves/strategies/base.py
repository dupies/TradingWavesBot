"""Strategy contract and plugin registry.

Adding a strategy means writing one class in this package and naming it in
`config/settings.yaml`. Nothing else in the codebase changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from tradingwaves.core.models import Candle, PositionAction, Position, Signal, SymbolSpec, Timeframe


@dataclass(frozen=True)
class StrategyContext:
    """Everything a strategy may know about the outside world.

    Passing this in rather than letting strategies reach for a broker or a
    clock is what keeps them testable and backtestable.
    """

    spec: SymbolSpec
    now: datetime
    spread_pips: float
    equity: float


@runtime_checkable
class Strategy(Protocol):
    name: str

    def required_timeframes(self) -> list[Timeframe]: ...

    def on_candle(self, candle: Candle, ctx: StrategyContext) -> Signal | None: ...

    def on_position_update(
        self, position: Position, candle: Candle, ctx: StrategyContext
    ) -> list[PositionAction]: ...


class UnknownStrategyError(KeyError):
    pass


_REGISTRY: dict[str, type] = {}


def register_strategy(name: str):
    def decorator(cls: type) -> type:
        if name in _REGISTRY:
            raise ValueError(f"strategy {name!r} is already registered")
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_strategy(name: str) -> type:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownStrategyError(
            f"unknown strategy {name!r}; available: {sorted(_REGISTRY)}"
        ) from None


def available_strategies() -> list[str]:
    return sorted(_REGISTRY)
