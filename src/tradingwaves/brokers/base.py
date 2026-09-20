"""The single interface every execution venue implements.

`sim_broker` (historical replay), `paper_broker` (live prices, simulated
fills) and `mt5_broker` (real orders) all satisfy this protocol, so the
strategy and risk code above them never changes between backtest, paper and
live.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tradingwaves.core.models import Candle, Direction, Position, SymbolSpec, TakeProfit, Timeframe


@runtime_checkable
class BrokerPort(Protocol):
    def account_equity(self) -> float: ...

    def symbol_spec(self, symbol: str) -> SymbolSpec: ...

    def current_spread_pips(self, symbol: str) -> float: ...

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int) -> list[Candle]: ...

    def open_position(
        self,
        symbol: str,
        direction: Direction,
        volume: float,
        stop_loss: float,
        take_profits: tuple[TakeProfit, ...],
        magic: int,
    ) -> Position: ...

    def close_partial(self, ticket: int, volume: float) -> object: ...

    def modify_stop(self, ticket: int, price: float) -> None: ...

    def open_positions(self) -> list[Position]: ...
