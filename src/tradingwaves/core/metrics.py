"""Backtest performance metrics.

Deliberately plain numbers. The one that matters most for a strategy like
this is max drawdown: a profit factor above 1 is worth nothing if the
drawdown along the way is larger than the account can survive.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingwaves.core.models import Fill, FillKind


@dataclass(frozen=True)
class BacktestMetrics:
    trades: int
    wins: int
    losses: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    net_profit: float
    max_drawdown: float
    expectancy: float

    def as_table(self) -> str:
        rows = [
            ("Trades", f"{self.trades}"),
            ("Wins / Losses", f"{self.wins} / {self.losses}"),
            ("Win rate", f"{self.win_rate:.1%}"),
            ("Gross profit", f"{self.gross_profit:,.2f}"),
            ("Gross loss", f"{self.gross_loss:,.2f}"),
            ("Net profit", f"{self.net_profit:,.2f}"),
            ("Profit factor", f"{self.profit_factor:.2f}"),
            ("Max drawdown", f"{self.max_drawdown:,.2f}"),
            ("Expectancy/trade", f"{self.expectancy:,.2f}"),
        ]
        width = max(len(label) for label, _ in rows)
        return "\n".join(f"{label.ljust(width)}  {value:>14}" for label, value in rows)


def compute_metrics(fills: list[Fill], starting_equity: float) -> BacktestMetrics:
    closes = [f for f in sorted(fills, key=lambda f: f.time) if f.kind is not FillKind.ENTRY]
    if not closes:
        return BacktestMetrics(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    gross_profit = sum(f.profit for f in closes if f.profit > 0)
    gross_loss = sum(f.profit for f in closes if f.profit < 0)
    wins = sum(1 for f in closes if f.profit > 0)
    losses = sum(1 for f in closes if f.profit < 0)
    net = gross_profit + gross_loss

    equity = starting_equity
    peak = starting_equity
    max_drawdown = 0.0
    for f in closes:
        equity += f.profit
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    if gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else 0.0
    else:
        profit_factor = gross_profit / abs(gross_loss)

    return BacktestMetrics(
        trades=len(closes),
        wins=wins,
        losses=losses,
        win_rate=wins / len(closes),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        net_profit=net,
        max_drawdown=max_drawdown,
        expectancy=net / len(closes),
    )
