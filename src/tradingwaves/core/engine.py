"""Orchestration: manage what is open, then look for what to open next.

The engine is deliberately thin. It owns no trading logic — strategies decide
what to trade, the risk engine decides how much, the broker executes and the
journal records. Its one real responsibility is ordering those steps and
keeping in-memory state honest against the broker.
"""

from __future__ import annotations

import logging

from tradingwaves.brokers.base import BrokerPort
from tradingwaves.core.journal import Journal
from tradingwaves.core.ladder import build_ladder
from tradingwaves.core.models import (
    Candle,
    ClosePartial,
    CloseAll,
    ModifyStop,
    Position,
    RejectCode,
    Signal,
)
from tradingwaves.core.risk import AccountState, RiskDecision, RiskEngine
from tradingwaves.strategies.base import Strategy, StrategyContext

log = logging.getLogger(__name__)


class Engine:
    def __init__(
        self,
        broker: BrokerPort,
        strategy: Strategy,
        risk: RiskEngine,
        journal: Journal,
        magic: int = 770001,
    ) -> None:
        self.broker = broker
        self.strategy = strategy
        self.risk = risk
        self.journal = journal
        self.magic = magic
        self.positions: list[Position] = []
        self.realized_pnl_today = 0.0
        self._current_day = None
        self._starting_balance = broker.account_equity()

    # ---- main loop ------------------------------------------------------

    def process_candle(self, candle: Candle) -> None:
        ctx = self._context(candle)
        self._collect_fills(candle)
        self._manage_open_positions(candle, ctx)
        self._look_for_entries(candle, ctx)

    def _collect_fills(self, candle: Candle) -> None:
        """Journal fills the venue produced on its own and roll the daily tally.

        Without this the daily loss cap would never see a loss, because stops
        fill inside the broker rather than through a call we make.
        """
        day = candle.time.date()
        if self._current_day is not None and day != self._current_day:
            self.realized_pnl_today = 0.0
            self._starting_balance = self.broker.account_equity()
        self._current_day = day

        for fill in self.broker.drain_fills():
            self.journal.record_fill(fill)
            self.realized_pnl_today = round(self.realized_pnl_today + fill.profit, 8)

    def _context(self, candle: Candle) -> StrategyContext:
        return StrategyContext(
            spec=self.broker.symbol_spec(candle.symbol),
            now=candle.time,
            spread_pips=self.broker.current_spread_pips(candle.symbol),
            equity=self.broker.account_equity(),
        )

    def _manage_open_positions(self, candle: Candle, ctx: StrategyContext) -> None:
        live = {p.ticket for p in self.broker.open_positions()}
        self.positions = [p for p in self.positions if p.ticket in live]

        for position in list(self.positions):
            if position.symbol != candle.symbol:
                continue
            for action in self.strategy.on_position_update(position, candle, ctx):
                self._apply(position, action)

    def _apply(self, position: Position, action) -> None:
        match action:
            case ModifyStop(price=price):
                self.broker.modify_stop(position.ticket, price)
                position.stop_loss = price
            case ClosePartial(volume=volume):
                fill = self.broker.close_partial(position.ticket, volume)
                self.journal.record_fill(fill)
            case CloseAll():
                fill = self.broker.close_partial(position.ticket, position.remaining_volume)
                self.journal.record_fill(fill)
            case _:
                log.warning("ignoring unknown position action: %r", action)

    def _look_for_entries(self, candle: Candle, ctx: StrategyContext) -> None:
        signal = self.strategy.on_candle(candle, ctx)
        if signal is None:
            self._journal_strategy_veto(candle)
            return
        self.submit(signal)

    def _journal_strategy_veto(self, candle: Candle) -> None:
        """A strategy that vetoed its own setup still owes an explanation."""
        reject = getattr(self.strategy, "last_reject", None)
        if not reject:
            return
        self.strategy.last_reject = None
        code, reason = reject
        self.journal.record_veto(
            symbol=candle.symbol,
            source=getattr(self.strategy, "name", "strategy"),
            at=candle.time,
            code=code,
            reason=reason,
        )

    # ---- signal execution ----------------------------------------------

    def submit(self, signal: Signal) -> Position | None:
        """Size, gate and execute a signal. Shared by strategies and by
        externally-supplied signals, so neither can bypass the risk rules."""
        spec = self.broker.symbol_spec(signal.symbol)
        signal_id = self.journal.record_signal(signal)

        account = AccountState(
            equity=self.broker.account_equity(),
            balance=self._starting_balance,
            realized_pnl_today=self.realized_pnl_today,
        )
        decision = self.risk.evaluate(signal, spec, account, self.positions)
        self.journal.record_decision(signal_id, decision)
        if not decision.approved:
            log.info("signal rejected (%s): %s", decision.code, decision.reason)
            return None

        ladder = build_ladder(decision.lot, [tp.price for tp in signal.take_profits], spec)
        if not ladder:
            self.journal.record_decision(
                signal_id,
                RiskDecision(
                    False,
                    decision.lot,
                    f"{decision.lot} lots cannot honour any take-profit level",
                    RejectCode.LOT_BELOW_MINIMUM,
                ),
            )
            return None

        position = self.broker.open_position(
            symbol=signal.symbol,
            direction=signal.direction,
            volume=decision.lot,
            stop_loss=signal.stop_loss,
            take_profits=ladder,
            magic=self.magic,
        )
        self.positions.append(position)
        self.journal.record_position(signal_id, position)
        return position

    # ---- startup --------------------------------------------------------

    def reconcile(self) -> list[Position]:
        """Rebuild in-memory state from the broker after a restart.

        The broker is the source of truth. Positions we cannot account for in
        the journal are logged and left alone — the bot never manages orders
        it did not place.
        """
        adopted: list[Position] = []
        for position in self.broker.open_positions():
            if position.magic != self.magic:
                log.info("ignoring position %s: foreign magic %s", position.ticket, position.magic)
                continue
            if self.journal.position_by_ticket(position.ticket) is None:
                log.warning("ignoring position %s: no journal record", position.ticket)
                continue
            adopted.append(position)

        known = {p.ticket for p in self.positions}
        self.positions.extend(p for p in adopted if p.ticket not in known)
        return adopted
