"""Core domain types.

Nothing here touches a broker, the network, or the clock. Times arrive as
parameters and are always timezone-aware UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Direction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        """+1 for a long, -1 for a short. Lets price maths stay direction-agnostic."""
        return 1 if self is Direction.BUY else -1


class Timeframe(StrEnum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


class FillKind(StrEnum):
    ENTRY = "ENTRY"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    MANUAL_CLOSE = "MANUAL_CLOSE"


class RejectCode(StrEnum):
    RANGE_TOO_SMALL = "RANGE_TOO_SMALL"
    RANGE_TOO_WIDE = "RANGE_TOO_WIDE"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    LOT_BELOW_MINIMUM = "LOT_BELOW_MINIMUM"
    DAILY_LOSS_CAP = "DAILY_LOSS_CAP"
    MAX_POSITIONS = "MAX_POSITIONS"
    MAX_EXPOSURE = "MAX_EXPOSURE"
    ALREADY_TRADED_TODAY = "ALREADY_TRADED_TODAY"
    SETUP_EXPIRED = "SETUP_EXPIRED"
    INVALID_SIGNAL = "INVALID_SIGNAL"


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: Timeframe
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class SymbolSpec:
    """Per-symbol contract details. The only place pips become prices."""

    symbol: str
    pip_size: float
    digits: int
    min_lot: float
    max_lot: float
    lot_step: float
    pip_value_per_lot: float

    def pips_to_price(self, pips: float) -> float:
        return pips * self.pip_size

    def price_to_pips(self, price_distance: float) -> float:
        return price_distance / self.pip_size

    def round_lot(self, lot: float) -> float:
        """Floor to the lot step. Returns 0.0 when the result is untradeable.

        Rounding down matters: rounding up would quietly risk more than the
        configured percentage.
        """
        if lot <= 0:
            return 0.0
        steps = int((lot + 1e-9) / self.lot_step)
        rounded = round(steps * self.lot_step, 8)
        if rounded < self.min_lot:
            return 0.0
        return min(rounded, self.max_lot)

    def round_price(self, price: float) -> float:
        return round(price, self.digits)


@dataclass(frozen=True)
class TakeProfit:
    price: float
    fraction: float
    index: int


@dataclass(frozen=True)
class Signal:
    symbol: str
    direction: Direction
    stop_loss: float
    take_profits: tuple[TakeProfit, ...]
    source: str
    created_at: datetime
    entry_price: float | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: Direction
    volume: float
    entry_price: float
    stop_loss: float
    take_profits: tuple[TakeProfit, ...]
    opened_at: datetime
    magic: int
    remaining_volume: float
    filled_tp_indexes: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class Fill:
    ticket: int
    time: datetime
    price: float
    volume: float
    kind: FillKind
    profit: float


@dataclass(frozen=True)
class ClosePartial:
    volume: float


@dataclass(frozen=True)
class ModifyStop:
    price: float


@dataclass(frozen=True)
class CloseAll:
    pass


PositionAction = ClosePartial | ModifyStop | CloseAll
