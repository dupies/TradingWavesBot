"""Take-profit ladder sizing.

A four-level ladder needs at least four minimum lots to execute. Brokers
enforce a minimum lot and a lot step, so a small position physically cannot
be closed in four pieces. Rather than entering a trade whose later partial
closes would be rejected, the ladder is shortened to what the size can
actually honour — keeping the nearest targets, dropping the furthest.
"""

from __future__ import annotations

from tradingwaves.core.models import SymbolSpec, TakeProfit


def build_ladder(lot: float, tp_prices: list[float], spec: SymbolSpec) -> tuple[TakeProfit, ...]:
    if lot < spec.min_lot or not tp_prices:
        return ()

    max_levels = min(int(round(lot / spec.min_lot, 8)), len(tp_prices))
    if max_levels <= 0:
        return ()

    prices = tp_prices[:max_levels]
    slice_lot = spec.round_lot(lot / max_levels) if max_levels > 1 else lot
    if slice_lot <= 0:
        slice_lot = spec.min_lot

    volumes = [slice_lot] * max_levels
    # Give the rounding remainder to the final level so the fractions always
    # close the whole position — never more, never less.
    volumes[-1] = round(lot - slice_lot * (max_levels - 1), 8)

    return tuple(
        TakeProfit(price=price, fraction=round(volume / lot, 10), index=index)
        for index, (price, volume) in enumerate(zip(prices, volumes))
    )
