"""Position sizing and hard risk limits.

Every signal passes through here regardless of origin, so a manually-sent
signal is subject to the same caps as a strategy-generated one.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingwaves.core.models import Direction, Position, RejectCode, Signal, SymbolSpec


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade_pct: float = 1.0
    daily_loss_cap_pct: float = 3.0
    max_concurrent_positions: int = 3
    max_total_exposure_pct: float = 10.0


@dataclass(frozen=True)
class AccountState:
    equity: float
    balance: float
    realized_pnl_today: float


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    lot: float
    reason: str | None = None
    code: RejectCode | None = None


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def evaluate(
        self,
        signal: Signal,
        spec: SymbolSpec,
        account: AccountState,
        open_positions: list[Position],
    ) -> RiskDecision:
        entry = signal.entry_price
        if entry is None:
            return RiskDecision(False, 0.0, "signal has no entry price", RejectCode.INVALID_SIGNAL)

        stop_distance = (entry - signal.stop_loss) * signal.direction.sign
        if stop_distance <= 0:
            return RiskDecision(
                False,
                0.0,
                f"stop {signal.stop_loss} is not below entry {entry} for a {signal.direction}",
                RejectCode.INVALID_SIGNAL,
            )

        loss_cap = account.balance * self.limits.daily_loss_cap_pct / 100
        if account.realized_pnl_today <= -loss_cap:
            return RiskDecision(
                False,
                0.0,
                f"daily loss {account.realized_pnl_today:.2f} breached cap of {loss_cap:.2f}",
                RejectCode.DAILY_LOSS_CAP,
            )

        if len(open_positions) >= self.limits.max_concurrent_positions:
            return RiskDecision(
                False,
                0.0,
                f"{len(open_positions)} positions open, limit is {self.limits.max_concurrent_positions}",
                RejectCode.MAX_POSITIONS,
            )

        stop_pips = spec.price_to_pips(stop_distance)
        risk_amount = account.equity * self.limits.risk_per_trade_pct / 100
        raw_lot = risk_amount / (stop_pips * spec.pip_value_per_lot)
        lot = spec.round_lot(raw_lot)

        if lot <= 0:
            return RiskDecision(
                False,
                0.0,
                f"sized {raw_lot:.4f} lots, below broker minimum of {spec.min_lot}",
                RejectCode.LOT_BELOW_MINIMUM,
            )

        # Exposure is measured as money at stake if every stop were hit, not as
        # notional value — notional is meaningless on a leveraged account.
        open_risk = sum(_position_risk(p, spec) for p in open_positions)
        total_risk = open_risk + risk_amount
        max_risk = account.equity * self.limits.max_total_exposure_pct / 100
        if total_risk > max_risk:
            return RiskDecision(
                False,
                0.0,
                f"total risk {total_risk:.2f} would exceed limit of {max_risk:.2f}",
                RejectCode.MAX_EXPOSURE,
            )

        return RiskDecision(True, lot, f"risking {risk_amount:.2f} over {stop_pips:.1f} pips")


def _position_risk(position: object, spec: SymbolSpec) -> float:
    """Money at stake on an open position if its stop is hit.

    Tolerates objects without the full Position shape so callers can pass
    lightweight stand-ins when only the count matters.
    """
    entry = getattr(position, "entry_price", None)
    stop = getattr(position, "stop_loss", None)
    volume = getattr(position, "remaining_volume", None)
    direction = getattr(position, "direction", None)
    if entry is None or stop is None or volume is None or direction is None:
        return 0.0

    distance = (entry - stop) * Direction(direction).sign
    if distance <= 0:  # stop at or beyond breakeven risks nothing
        return 0.0
    return spec.price_to_pips(distance) * spec.pip_value_per_lot * volume
