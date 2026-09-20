"""Historical replay broker.

Drives a backtest one candle at a time and simulates fills against each
candle's range. Deliberately pessimistic where a single candle is ambiguous:
if a candle touches both the stop and a take-profit, the stop wins, because
tick order inside the candle is unknowable and flattering a backtest is how
strategies look profitable right up until they trade real money.
"""

from __future__ import annotations

from tradingwaves.core.models import (
    Candle,
    Direction,
    Fill,
    FillKind,
    Position,
    SymbolSpec,
    TakeProfit,
    Timeframe,
)


class SimBroker:
    def __init__(
        self,
        candles: list[Candle],
        spec: SymbolSpec,
        starting_equity: float = 10_000.0,
        spread_pips: float = 1.0,
    ) -> None:
        self._candles = list(candles)
        self._spec = spec
        self._index = -1
        self._positions: list[Position] = []
        self._next_ticket = 1
        self.starting_equity = starting_equity
        self.spread_pips = spread_pips
        self.realized_pnl = 0.0
        self.fills: list[Fill] = []

    # ---- replay control -------------------------------------------------

    def advance(self) -> Candle | None:
        """Step forward one candle, settling open positions against it first."""
        if self._index + 1 >= len(self._candles):
            return None
        self._index += 1
        candle = self._candles[self._index]
        self._settle(candle)
        return candle

    @property
    def current_candle(self) -> Candle | None:
        if self._index < 0:
            return None
        return self._candles[self._index]

    @property
    def current_time(self):
        candle = self.current_candle
        return candle.time if candle else None

    # ---- BrokerPort -----------------------------------------------------

    def account_equity(self) -> float:
        return self.starting_equity + self.realized_pnl

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        return self._spec

    def current_spread_pips(self, symbol: str) -> float:
        return self.spread_pips

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int) -> list[Candle]:
        if self._index < 0:
            return []
        start = max(0, self._index + 1 - count)
        return self._candles[start : self._index + 1]

    def open_position(
        self,
        symbol: str,
        direction: Direction,
        volume: float,
        stop_loss: float,
        take_profits: tuple[TakeProfit, ...],
        magic: int,
    ) -> Position:
        entry = self._entry_price(direction)
        position = Position(
            ticket=self._next_ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profits=take_profits,
            opened_at=self._entry_time(),
            magic=magic,
            remaining_volume=volume,
        )
        self._next_ticket += 1
        self._positions.append(position)
        self.fills.append(
            Fill(position.ticket, position.opened_at, entry, volume, FillKind.ENTRY, 0.0)
        )
        return position

    def close_partial(self, ticket: int, volume: float) -> Fill:
        position = self._by_ticket(ticket)
        price = self._exit_price(position.direction)
        return self._close(position, volume, price, FillKind.MANUAL_CLOSE)

    def modify_stop(self, ticket: int, price: float) -> None:
        self._by_ticket(ticket).stop_loss = price

    def open_positions(self) -> list[Position]:
        return list(self._positions)

    # ---- internals ------------------------------------------------------

    def _by_ticket(self, ticket: int) -> Position:
        for position in self._positions:
            if position.ticket == ticket:
                return position
        raise KeyError(f"no open position with ticket {ticket}")

    def _half_spread(self) -> float:
        return self._spec.pips_to_price(self.spread_pips) / 2

    def _entry_price(self, direction: Direction) -> float:
        """Fill at the next candle's open — a decision made on a closed candle
        cannot be executed inside it."""
        nxt = self._index + 1
        base = self._candles[nxt].open if nxt < len(self._candles) else self._candles[self._index].close
        return round(base + self._half_spread() * direction.sign, self._spec.digits + 1)

    def _entry_time(self):
        nxt = self._index + 1
        return self._candles[nxt].time if nxt < len(self._candles) else self._candles[self._index].time

    def _exit_price(self, direction: Direction) -> float:
        candle = self._candles[self._index]
        return round(candle.close - self._half_spread() * direction.sign, self._spec.digits + 1)

    def _settle(self, candle: Candle) -> None:
        for position in list(self._positions):
            if position.symbol != candle.symbol:
                continue
            if self._stop_hit(position, candle):
                self._close(position, position.remaining_volume, position.stop_loss, FillKind.STOP_LOSS)
                continue
            self._fill_take_profits(position, candle)

    def _stop_hit(self, position: Position, candle: Candle) -> bool:
        if position.direction is Direction.BUY:
            return candle.low <= position.stop_loss
        return candle.high >= position.stop_loss

    def _fill_take_profits(self, position: Position, candle: Candle) -> None:
        for tp in position.take_profits:
            if tp.index in position.filled_tp_indexes:
                continue
            reached = (
                candle.high >= tp.price
                if position.direction is Direction.BUY
                else candle.low <= tp.price
            )
            if not reached:
                continue
            volume = min(round(position.volume * tp.fraction, 8), position.remaining_volume)
            if volume <= 0:
                continue
            position.filled_tp_indexes.append(tp.index)
            self._close(position, volume, tp.price, FillKind.TAKE_PROFIT)
            if position.remaining_volume <= 0:
                return

    def _close(self, position: Position, volume: float, price: float, kind: FillKind) -> Fill:
        volume = min(volume, position.remaining_volume)
        profit = (
            (price - position.entry_price)
            * position.direction.sign
            / self._spec.pip_size
            * self._spec.pip_value_per_lot
            * volume
        )
        self.realized_pnl = round(self.realized_pnl + profit, 8)
        position.remaining_volume = round(position.remaining_volume - volume, 8)
        fill = Fill(position.ticket, self._candles[self._index].time, price, volume, kind, profit)
        self.fills.append(fill)
        if position.remaining_volume <= 0:
            self._positions.remove(position)
        return fill
