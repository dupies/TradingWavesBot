"""1H opening-range breakout.

Mark the high and low of the session's opening hour. If a following candle
closes outside that range, trade the break with the stop on the far side of
the range and a laddered take-profit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from zoneinfo import ZoneInfo

from tradingwaves.core.models import (
    Candle,
    Direction,
    ModifyStop,
    Position,
    PositionAction,
    RejectCode,
    Signal,
    TakeProfit,
    Timeframe,
)
from tradingwaves.strategies.base import StrategyContext, register_strategy


class SetupState(StrEnum):
    IDLE = "IDLE"
    RANGE_MARKED = "RANGE_MARKED"
    TRADED = "TRADED"
    ABANDONED = "ABANDONED"


@dataclass(frozen=True)
class Range1HConfig:
    session_hour: int = 8
    session_timezone: str = "Europe/London"
    confirmation_window: int = 3
    tp_pips: tuple[float, ...] = (100.0, 200.0, 300.0, 400.0)
    sl_buffer_pips: float = 2.0
    min_range_pips: float = 5.0
    max_range_pips: float = 60.0
    max_spread_pips: float = 3.0
    breakeven_after_tp1: bool = True


@dataclass
class _Setup:
    session_date: date
    state: SetupState = SetupState.IDLE
    high: float = 0.0
    low: float = 0.0
    attempts: int = 0


@register_strategy("range_1h")
class Range1H:
    name = "range_1h"

    def __init__(self, config: Range1HConfig | None = None) -> None:
        self.config = config or Range1HConfig()
        self._tz = ZoneInfo(self.config.session_timezone)
        self._setups: dict[str, _Setup] = {}
        self.last_reject: tuple[RejectCode, str] | None = None

    def required_timeframes(self) -> list[Timeframe]:
        return [Timeframe.H1]

    # ---- entry ----------------------------------------------------------

    def on_candle(self, candle: Candle, ctx: StrategyContext) -> Signal | None:
        local = candle.time.astimezone(self._tz)
        setup = self._setups.get(candle.symbol)

        if setup is None or setup.session_date != local.date():
            setup = _Setup(session_date=local.date())
            self._setups[candle.symbol] = setup

        if setup.state is SetupState.IDLE:
            if local.hour == self.config.session_hour:
                setup.high = candle.high
                setup.low = candle.low
                setup.state = SetupState.RANGE_MARKED
            return None

        if setup.state is not SetupState.RANGE_MARKED:
            return None

        if candle.close > setup.high:
            return self._build_signal(candle, ctx, setup, Direction.BUY)
        if candle.close < setup.low:
            return self._build_signal(candle, ctx, setup, Direction.SELL)

        setup.attempts += 1
        if setup.attempts >= self.config.confirmation_window:
            setup.state = SetupState.ABANDONED
        return None

    def _build_signal(
        self, candle: Candle, ctx: StrategyContext, setup: _Setup, direction: Direction
    ) -> Signal | None:
        spec = ctx.spec
        range_pips = spec.price_to_pips(setup.high - setup.low)

        if range_pips < self.config.min_range_pips:
            return self._reject(
                setup,
                RejectCode.RANGE_TOO_SMALL,
                f"range {range_pips:.1f} pips is below minimum {self.config.min_range_pips}",
            )
        if range_pips > self.config.max_range_pips:
            return self._reject(
                setup,
                RejectCode.RANGE_TOO_WIDE,
                f"range {range_pips:.1f} pips exceeds maximum {self.config.max_range_pips}",
            )
        if ctx.spread_pips > self.config.max_spread_pips:
            return self._reject(
                setup,
                RejectCode.SPREAD_TOO_WIDE,
                f"spread {ctx.spread_pips:.1f} pips exceeds maximum {self.config.max_spread_pips}",
            )

        entry = candle.close
        buffer = spec.pips_to_price(self.config.sl_buffer_pips)
        stop = setup.low - buffer if direction is Direction.BUY else setup.high + buffer

        fraction = 1.0 / len(self.config.tp_pips)
        take_profits = tuple(
            TakeProfit(
                price=spec.round_price(entry + spec.pips_to_price(pips) * direction.sign),
                fraction=fraction,
                index=i,
            )
            for i, pips in enumerate(self.config.tp_pips)
        )

        setup.state = SetupState.TRADED
        self.last_reject = None
        return Signal(
            symbol=candle.symbol,
            direction=direction,
            stop_loss=spec.round_price(stop),
            take_profits=take_profits,
            source=self.name,
            created_at=candle.time,
            entry_price=entry,
            meta={"range_high": setup.high, "range_low": setup.low, "range_pips": range_pips},
        )

    def _reject(self, setup: _Setup, code: RejectCode, reason: str) -> None:
        setup.state = SetupState.ABANDONED
        self.last_reject = (code, reason)
        return None

    # ---- management -----------------------------------------------------

    def on_position_update(
        self, position: Position, candle: Candle, ctx: StrategyContext
    ) -> list[PositionAction]:
        if not self.config.breakeven_after_tp1:
            return []
        if not position.filled_tp_indexes:
            return []

        # Stateless check, so it survives a restart: if the stop already sits
        # at or beyond entry in the profitable direction, there is nothing to do.
        already_safe = (position.stop_loss - position.entry_price) * position.direction.sign >= 0
        if already_safe:
            return []

        return [ModifyStop(position.entry_price)]
