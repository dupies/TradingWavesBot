# TradingWavesBot — Design

**Date:** 2026-09-20
**Status:** Approved for implementation planning

## Purpose

An automated MetaTrader 5 trading bot that runs the 1H opening-range breakout
strategy, accepts externally-supplied daily signals, and is built so that new
strategies and new signal sources can be added without modifying existing code.

The system must also support parameter optimization against historical data and
a paper-trading mode that runs on live prices without placing real orders.

## Constraints and decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Platform | MetaTrader 5 | Official Python API; MT4 has none |
| Language | Python 3.11+ | Required by the `MetaTrader5` package |
| Runtime host | Windows VPS | The `MetaTrader5` package is Windows-only; the developer's machine is macOS |
| Development host | macOS | Full test suite runs without MT5 installed |
| Instruments | Forex pairs, distances in pips | Per user |
| Account | None yet; demo first | Live trading is gated on backtest and paper results |

### Open risk: target distances

The specified targets of 100/200/300/400 pips are large relative to a 1H
breakout. EURUSD's average daily range is roughly 70–90 pips, so TP1 would
typically require 1–3 days and TP4 considerably longer, holding the position
across many sessions.

These values are implemented as configurable defaults, not constants. Phase 2
optimization is expected to produce evidence-based replacements. This is
recorded as a known risk, not a blocker.

## Architecture

Approach: a pure domain core surrounded by adapters. The core contains no
MetaTrader imports and no I/O, which makes it testable on any machine and
reusable across live, paper and historical execution.

```
config/
  settings.yaml        runtime configuration
  symbols.yaml         per-symbol pip size, lot step, session hours
  .env                 secrets — never committed

src/
  core/                pure Python, no broker imports
    models.py          Candle, Timeframe, Signal, Position, Fill,
                       RiskDecision, PositionAction, StrategyContext
    risk.py            position sizing, daily loss cap, exposure limits
    engine.py          orchestration: poll -> strategy -> risk -> execute
    journal.py         SQLite record of every decision, veto and fill
  brokers/
    base.py            BrokerPort protocol
    mt5_broker.py      live implementation; the only file importing MetaTrader5
    paper_broker.py    live prices, simulated fills
    sim_broker.py      historical replay, simulated fills
  strategies/
    base.py            Strategy protocol and registry
    range_1h.py        the 1H opening-range strategy
  signals/
    base.py            SignalSource protocol and registry
    manual.py          Telegram bot and CLI intake
    channel.py         channel subscription and scraping
    parser.py          text -> Signal, with confidence scoring
  optimize/
    sweep.py           parameter grid search via sim_broker
    walkforward.py     rolling in-sample / out-of-sample evaluation
    report.py          performance metrics and overfitting warnings
  notify/
    telegram.py        entry, TP, SL and daily-summary alerts

tests/                 pytest; runs on macOS with no MT5 present
scripts/
  backtest.py
  optimize.py
  run_live.py
```

### Data flow

Strategy-generated signals and externally-supplied signals converge on a single
path, so both are subject to identical risk controls:

```
Strategy.on_candle()  ─┐
                       ├─> Signal ─> RiskEngine ─> BrokerPort ─> Journal ─> Notify
SignalSource.poll()   ─┘             (sizes or
                                      vetoes)
```

A manually-sent signal cannot bypass the daily loss cap.

### Broker implementations

| Implementation | Market data | Orders | Purpose |
| --- | --- | --- | --- |
| `mt5_broker` | Live | Real | Demo and live trading |
| `paper_broker` | Live | Simulated | Practice mode on real-time prices |
| `sim_broker` | Historical | Simulated | Backtesting and optimization |

All three satisfy `BrokerPort`. Selection is a single value in `settings.yaml`.
Strategy, risk and journal code is identical across all three, so paper-mode
behaviour is a faithful preview of live behaviour, and backtests exercise the
code that actually trades.

### State reconciliation

The broker is the source of truth for open positions; local state is a cache.

On every startup the engine queries MT5 for open positions, matches them to
journal records by magic number, and rebuilds in-memory state from the result.
A restart during a partially-closed scale-out — TP1 and TP2 filled, 50% still
running — resumes with correct remaining volume and stop placement rather than
orphaning the position.

Positions found at the broker with no matching journal record are logged and
left untouched; the bot never manages orders it cannot account for.

## The 1H range strategy

### Setup

At the configured session hour, mark the high and low of that 1H candle.
Default is the London open, 08:00 in the configured timezone, translated to
broker server time at runtime. The hour, timezone and symbol set are
configuration.

### Entry

The next 1H candle after the range candle is the confirmation candle.

- Closes above the range high: enter long at market on the next candle's open.
- Closes below the range low: enter short at market on the next candle's open.
- Closes inside the range: continue evaluating subsequent candles for up to
  `confirmation_window` candles (default 3), then abandon the setup for the day.

### Exits

- Stop-loss at the opposite side of the range — range low for longs, range high
  for shorts — offset by `sl_buffer_pips` to allow for spread.
- Take-profit ladder, closing 25% of the position at each level. Defaults are
  100, 200, 300 and 400 pips from entry.
- When TP1 fills, the stop moves to breakeven. Configurable via
  `breakeven_after_tp1`.

### Guards

Each of these vetoes the trade and writes the reason to the journal:

- `min_range_pips` — reject ranges too small to be meaningful.
- `max_range_pips` — reject ranges so wide that fixed-percentage risk yields an
  untradeable lot size.
- `max_spread_pips` — reject entry when the spread is abnormally wide.
- One trade per symbol per day. Setups expire at the end of the trading day.

### Lot-splitting feasibility

Brokers enforce a minimum lot (typically 0.01) and a lot step. A position of
0.03 lots cannot be divided into four equal exits.

Before entry the strategy checks whether the risk-derived size supports the full
four-level ladder. If it does not, the ladder is reduced to the
largest number of levels the size can honour, keeping the nearest levels and
dropping the furthest — a 0.03-lot position runs TP1, TP2 and TP3 at 0.01 each.
The reduction is journalled. The bot does not enter with a ladder it cannot
execute.

## Risk engine

Applied to every signal regardless of origin.

```
lot = (equity × risk_pct) ÷ (sl_distance_pips × pip_value_per_lot)
```

Rounded down to the broker's lot step, and rejected if below the minimum lot.

Hard limits:

- `risk_per_trade_pct` — default 1% of equity.
- `daily_loss_cap_pct` — default 3%. On breach, no new positions are opened for
  the remainder of the trading day; existing positions continue to be managed.
- `max_concurrent_positions`.
- `max_total_exposure_pct`.

Every rejection is journalled with a machine-readable reason code, so any
absent trade can be explained after the fact.

## Extension points

Three protocols, each defined in one file. Adding an implementation requires no
changes to existing modules.

### Strategy

```python
@register_strategy("range_1h")
class Range1H(Strategy):
    def required_timeframes(self) -> list[Timeframe]: ...
    def on_candle(self, candle: Candle, ctx: StrategyContext) -> Signal | None: ...
    def on_position_update(self, pos: Position, ctx: StrategyContext) -> list[PositionAction]: ...
```

`on_position_update` returns actions such as partial closes, stop modifications
and time-based exits. Trailing stops, when wanted, are implemented here inside a
single strategy rather than in the engine.

Strategies are enabled per symbol in `settings.yaml`.

### Signal source

```python
@register_source("telegram_manual")
class TelegramManual(SignalSource):
    def poll(self) -> list[RawSignal]: ...
```

Sourcing is separate from parsing. `parser.py` converts raw text into a `Signal`
and attaches a confidence score. Parses below the confidence threshold — missing
stop-loss, ambiguous symbol, unparseable direction — are not executed; they are
queued and pushed to the operator for explicit confirmation or rejection.

Signal-provider message formats change without notice. Holding low-confidence
parses prevents a reworded message from producing a wrong trade.

### Broker

Implementing `BrokerPort` adds a venue. The interface covers candle retrieval,
position opening, partial closing, stop modification, open-position query and
account equity.

## Testing

Test-driven development throughout. `pytest`, no MT5 dependency, full suite runs
on macOS.

- Unit tests for risk sizing, cap enforcement and lot-step rounding.
- Strategy rule tests driven by fixed historical candle fixtures, covering each
  entry condition, each guard, ladder reduction and breakeven movement.
- Engine tests against `sim_broker`, including restart-and-reconcile with a
  partially closed position.
- Parser tests over a corpus of real and malformed signal messages, asserting
  correct confidence scoring.

## Delivery phases

Each phase is independently useful and independently verifiable.

| Phase | Deliverable | Host | Prerequisites |
| --- | --- | --- | --- |
| 1 | Core models, risk engine, journal, `sim_broker`, `range_1h`, test suite | macOS | None |
| 2 | Backtest runner, parameter sweep, walk-forward report | macOS | Historical data |
| 3 | `mt5_broker`, startup reconciliation, `paper_broker` | Windows VPS | Demo account, VPS |
| 4 | Signal intake: manual Telegram, then channel parsing | VPS | Telegram bot token |
| 5 | Notifications, process supervision, deployment runbook | VPS | Phase 3 |

Phases 1 and 2 require neither a broker account nor a VPS, so the strategy is
evaluated on historical evidence before any money is spent on infrastructure.

Progression to live trading is gated: backtest, then optimization with
acceptable out-of-sample results, then paper trading, then demo, then live.

## Out of scope

- MT4 support. The architecture permits it via a new `BrokerPort`
  implementation, but no MT4 adapter is planned.
- Economic news filtering. A likely future extension point; not in these phases.
- Machine-learning trade filtering. Considered and deferred.
- Web dashboard. Telegram notifications and the SQLite journal cover
  observability for now.
